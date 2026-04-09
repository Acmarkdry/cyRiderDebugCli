"""Crash analysis command handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rider_debug_mcp.middleware.models import CommandResult, CommandStatus, ParsedCommand
from rider_debug_mcp.middleware.router import BaseHandler

if TYPE_CHECKING:
    from rider_debug_mcp.analysis.crash import CrashAnalyzer


class AnalysisHandler(BaseHandler):
    """Handles crash analysis commands."""

    def __init__(self, crash_analyzer: CrashAnalyzer) -> None:
        self._analyzer = crash_analyzer

    def get_commands(self) -> list[str]:
        return ["analyze_crash", "crash_report", "crash_history"]

    async def handle(self, command: ParsedCommand) -> CommandResult:
        handler_map = {
            "analyze_crash": self._analyze,
            "crash_report": self._report,
            "crash_history": self._history,
        }
        handler_fn = handler_map[command.name]
        return await handler_fn(command)

    async def _analyze(self, command: ParsedCommand) -> CommandResult:
        report = await self._analyzer.analyze_latest()
        if report is None:
            return CommandResult(
                status=CommandStatus.SUCCESS,
                message="No crash detected in current session",
                command_name=command.name,
            )
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=report.model_dump(),
            message=f"Crash analyzed: {report.summary}",
            command_name=command.name,
        )

    async def _report(self, command: ParsedCommand) -> CommandResult:
        report = self._analyzer.get_latest_report()
        if report is None:
            return CommandResult(
                status=CommandStatus.SUCCESS,
                message="No crash reports available",
                command_name=command.name,
            )
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=report.model_dump(),
            message=report.summary,
            command_name=command.name,
        )

    async def _history(self, command: ParsedCommand) -> CommandResult:
        reports = self._analyzer.get_history()
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=[
                {"report_id": r.report_id, "summary": r.summary, "timestamp": r.timestamp}
                for r in reports
            ],
            message=f"{len(reports)} crash report(s) in history",
            command_name=command.name,
        )
