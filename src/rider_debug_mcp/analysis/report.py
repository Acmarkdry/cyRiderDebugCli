"""Crash report generator – turns CrashContext into structured CrashReport."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from rider_debug_mcp.analysis.models import (
    CrashContext,
    CrashReport,
    ExceptionInfo,
    FrameCategory,
)


class ReportGenerator:
    """Generates structured :class:`CrashReport` from :class:`CrashContext`."""

    def generate(self, ctx: CrashContext) -> CrashReport:
        """Generate a crash report from collected context.

        Args:
            ctx: The crash context.

        Returns:
            A fully populated :class:`CrashReport`.
        """
        # Build exception chain (single exception for now; extend for inner exceptions)
        exception_chain = [
            ExceptionInfo(
                exception_type=ctx.exception_type,
                message=ctx.exception_message,
            )
        ]

        # Find the crash entry point for summary
        entry_frame = next((f for f in ctx.annotated_frames if f.is_entry_point), None)
        summary = self._build_summary(ctx, entry_frame)

        # Generate investigation suggestions
        suggestions = self._build_suggestions(ctx, entry_frame)

        return CrashReport(
            report_id=f"cr-{uuid.uuid4().hex[:8]}",
            summary=summary,
            exception_chain=exception_chain,
            annotated_stack=ctx.annotated_frames,
            variable_snapshot=ctx.variables,
            investigation_suggestions=suggestions,
            timestamp=datetime.now(UTC).isoformat(),
            crash_context=ctx,
        )

    @staticmethod
    def _build_summary(ctx: CrashContext, entry_frame=None) -> str:
        """Build a 1-2 sentence crash summary."""
        location = ""
        if entry_frame:
            parts = []
            if entry_frame.class_name:
                parts.append(entry_frame.class_name)
            parts.append(entry_frame.method_name)
            location = ".".join(parts)
            if entry_frame.line:
                location += f" at line {entry_frame.line}"

        if location:
            return f"{ctx.exception_type} in {location}: {ctx.exception_message}"
        return f"{ctx.exception_type}: {ctx.exception_message}"

    @staticmethod
    def _build_suggestions(ctx: CrashContext, entry_frame=None) -> list[str]:
        """Generate investigation suggestions based on the crash context."""
        suggestions: list[str] = []

        # Suggest based on exception type
        exc_type = ctx.exception_type
        if "NullReference" in exc_type:
            suggestions.append("Check for null references before accessing object members")
            if entry_frame and entry_frame.file:
                suggestions.append(f"Add null checks in {entry_frame.file} around line {entry_frame.line}")
        elif "IndexOutOfRange" in exc_type:
            suggestions.append("Verify array/list bounds before accessing elements")
        elif "InvalidOperation" in exc_type:
            suggestions.append("Check object state before performing the operation")
        elif "FileNotFound" in exc_type or "DirectoryNotFound" in exc_type:
            suggestions.append("Verify the file/directory path exists before accessing it")
        elif "Timeout" in exc_type:
            suggestions.append("Check network connectivity and consider increasing timeout values")
        elif "StackOverflow" in exc_type:
            suggestions.append("Look for infinite recursion in the call chain")
        elif "OutOfMemory" in exc_type:
            suggestions.append("Profile memory usage; look for memory leaks or excessive allocations")

        # If we have user-code frames, suggest examining them
        user_frames = [f for f in ctx.annotated_frames if f.category == FrameCategory.USER_CODE]
        if user_frames and len(user_frames) > 1:
            suggestions.append(
                f"Examine the {len(user_frames)} user-code frames in the stack trace for context"
            )

        # If variables were collected, suggest checking them
        if ctx.variables:
            suggestions.append(f"Review the {len(ctx.variables)} captured variable(s) at the crash point")

        # If breakpoints were active, they might be relevant
        if ctx.breakpoint_history:
            suggestions.append(
                f"Consider the {len(ctx.breakpoint_history)} active breakpoint(s) for additional context"
            )

        # Generic suggestion
        if not suggestions:
            suggestions.append("Set a breakpoint near the crash location and reproduce the issue")

        return suggestions
