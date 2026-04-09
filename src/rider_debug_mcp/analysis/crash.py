"""Crash analysis engine – detects crashes and collects context."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from rider_debug_mcp.analysis.models import (
    AnnotatedStackFrame,
    CrashContext,
    CrashReport,
    FrameCategory,
)
from rider_debug_mcp.gateway.events import ExceptionEvent, ProcessExitEvent

if TYPE_CHECKING:
    from rider_debug_mcp.analysis.report import ReportGenerator
    from rider_debug_mcp.gateway.client import RiderClient
    from rider_debug_mcp.middleware.session import SessionManager

logger = logging.getLogger(__name__)

# Namespaces considered framework code (not user code)
FRAMEWORK_NAMESPACES = frozenset({
    "System",
    "Microsoft",
    "UnityEngine",
    "UnityEditor",
    "Mono",
    "NUnit",
    "mscorlib",
})

# Regex for parsing .NET stack trace lines
# e.g.  "   at Namespace.Class.Method(args) in C:\path\file.cs:line 42"
_FRAME_RE = re.compile(
    r"^\s*at\s+"
    r"(?P<fullmethod>(?P<ns>[\w.]+)\.(?P<class>\w+)\.(?P<method>\w+))"
    r"(?:\((?P<params>[^)]*)\))?"
    r"(?:\s+in\s+(?P<file>.+?):line\s+(?P<line>\d+))?"
    r"\s*$",
)


def parse_dotnet_stack_trace(
    raw: str,
    user_namespace_patterns: list[str] | None = None,
) -> list[AnnotatedStackFrame]:
    """Parse a raw .NET stack trace string into annotated frames.

    Args:
        raw: The raw stack trace text.
        user_namespace_patterns: Optional list of namespace prefixes to treat as user code.
            If ``None``, any namespace NOT in :data:`FRAMEWORK_NAMESPACES` is user code.

    Returns:
        A list of :class:`AnnotatedStackFrame` objects.
    """
    frames: list[AnnotatedStackFrame] = []
    first_user_found = False

    for idx, line in enumerate(raw.splitlines()):
        m = _FRAME_RE.match(line)
        if not m:
            continue

        ns = m.group("ns") or ""
        class_name = m.group("class") or ""
        method_name = m.group("method") or m.group("fullmethod")
        file = m.group("file")
        line_no = int(m.group("line")) if m.group("line") else None

        # Determine category
        top_ns = ns.split(".")[0] if ns else ""
        if user_namespace_patterns:
            is_user = any(ns.startswith(p) for p in user_namespace_patterns)
        else:
            is_user = top_ns not in FRAMEWORK_NAMESPACES and top_ns != ""

        category = FrameCategory.USER_CODE if is_user else FrameCategory.FRAMEWORK_CODE
        is_entry = is_user and not first_user_found
        if is_entry:
            first_user_found = True

        frames.append(
            AnnotatedStackFrame(
                index=len(frames),
                namespace=ns or None,
                class_name=class_name or None,
                method_name=method_name,
                file=file,
                line=line_no,
                category=category,
                is_entry_point=is_entry,
            )
        )

    return frames


class CrashAnalyzer:
    """Crash analysis engine.

    Subscribes to debug events, collects crash context, and generates reports.
    Also stores crash history in-memory for the duration of the session.
    """

    def __init__(
        self,
        client: RiderClient,
        session: SessionManager,
        report_generator: ReportGenerator,
    ) -> None:
        self._client = client
        self._session = session
        self._report_gen = report_generator
        self._history: list[CrashReport] = []
        self._latest_context: CrashContext | None = None

    # --- Event handlers (called by EventListener) ---

    async def on_exception(self, event: ExceptionEvent) -> None:
        """Handle an exception event from the debug event stream."""
        logger.info("Exception detected: %s – %s", event.exception_type, event.message)
        ctx = await self._collect_context(event)
        self._latest_context = ctx
        report = self._report_gen.generate(ctx)
        self._history.append(report)
        logger.info("Crash report generated: %s", report.report_id)

    async def on_process_exit(self, event: ProcessExitEvent) -> None:
        """Handle a process exit event."""
        if event.is_abnormal:
            logger.info("Abnormal process exit (code %d)", event.exit_code)
            ctx = CrashContext(
                exception_type="ProcessExit",
                exception_message=f"Process exited with code {event.exit_code}",
                timestamp=event.timestamp,
                data_completeness={"stack_trace": "unavailable: process already exited"},
            )
            self._latest_context = ctx
            report = self._report_gen.generate(ctx)
            self._history.append(report)

    # --- Public API ---

    async def analyze_latest(self) -> CrashReport | None:
        """Re-analyze the latest crash context, or return ``None`` if no crash."""
        if self._latest_context is None:
            return None
        report = self._report_gen.generate(self._latest_context)
        # Replace the last report
        if self._history:
            self._history[-1] = report
        else:
            self._history.append(report)
        return report

    def get_latest_report(self) -> CrashReport | None:
        """Return the most recent crash report."""
        return self._history[-1] if self._history else None

    def get_history(self) -> list[CrashReport]:
        """Return all crash reports from the current session."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear crash history."""
        self._history.clear()
        self._latest_context = None

    # --- Internal ---

    async def _collect_context(self, event: ExceptionEvent) -> CrashContext:
        """Collect as much context as possible after a crash."""
        completeness: dict[str, str] = {}

        # Parse stack trace
        annotated_frames: list[AnnotatedStackFrame] = []
        if event.stack_trace:
            annotated_frames = parse_dotnet_stack_trace(event.stack_trace)
            completeness["stack_trace"] = "collected"
        else:
            completeness["stack_trace"] = "unavailable: no stack trace in event"

        # Collect variables
        variables = []
        try:
            variables = await self._client.get_variables()
            completeness["variables"] = "collected"
        except Exception as exc:
            completeness["variables"] = f"unavailable: {exc}"

        # Breakpoint history from session
        bp_history = [bp.id for bp in self._session.breakpoints]

        return CrashContext(
            exception_type=event.exception_type,
            exception_message=event.message,
            raw_stack_trace=event.stack_trace,
            annotated_frames=annotated_frames,
            variables=variables,
            thread_id=event.thread_id,
            breakpoint_history=bp_history,
            timestamp=event.timestamp,
            data_completeness=completeness,
        )
