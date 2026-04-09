"""Breakpoint management command handler."""

from __future__ import annotations

from rider_debug_mcp.gateway.client import RiderClient
from rider_debug_mcp.middleware.models import CommandResult, CommandStatus, ParsedCommand
from rider_debug_mcp.middleware.router import BaseHandler
from rider_debug_mcp.middleware.session import SessionManager


class BreakpointHandler(BaseHandler):
    """Handles breakpoint management commands."""

    def __init__(self, client: RiderClient, session: SessionManager) -> None:
        self._client = client
        self._session = session

    def get_commands(self) -> list[str]:
        return [
            "add_breakpoint",
            "remove_breakpoint",
            "enable_breakpoint",
            "disable_breakpoint",
            "list_breakpoints",
            "clear_breakpoints",
        ]

    async def handle(self, command: ParsedCommand) -> CommandResult:
        handler_map = {
            "add_breakpoint": self._add,
            "remove_breakpoint": self._remove,
            "enable_breakpoint": self._enable,
            "disable_breakpoint": self._disable,
            "list_breakpoints": self._list,
            "clear_breakpoints": self._clear,
        }
        handler_fn = handler_map[command.name]
        return await handler_fn(command)

    async def _add(self, command: ParsedCommand) -> CommandResult:
        # Resolve file from context or positional args
        file = command.context_target
        args = list(command.positional_args)

        if file is None:
            if len(args) < 2:
                return CommandResult(
                    status=CommandStatus.ERROR,
                    message="Usage: add_breakpoint <file> <line> [--condition <expr>]",
                    command_name=command.name,
                )
            file = args.pop(0)

        if not args:
            return CommandResult(
                status=CommandStatus.ERROR,
                message="Missing line number",
                command_name=command.name,
            )

        try:
            line = int(args[0])
        except ValueError:
            return CommandResult(
                status=CommandStatus.ERROR,
                message=f"Invalid line number: {args[0]}",
                command_name=command.name,
            )

        condition = command.named_args.get("condition")
        bp = await self._client.add_breakpoint(file, line, condition)
        self._session.cache_breakpoint(bp)

        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=bp.model_dump(),
            message=f"Breakpoint {bp.id} added at {file}:{line}" + (f" (condition: {condition})" if condition else ""),
            command_name=command.name,
        )

    async def _remove(self, command: ParsedCommand) -> CommandResult:
        if not command.positional_args:
            return CommandResult(
                status=CommandStatus.ERROR,
                message="Usage: remove_breakpoint <id>",
                command_name=command.name,
            )
        bp_id = command.positional_args[0]
        await self._client.remove_breakpoint(bp_id)
        self._session.remove_breakpoint(bp_id)
        return CommandResult(
            status=CommandStatus.SUCCESS,
            message=f"Breakpoint {bp_id} removed",
            command_name=command.name,
        )

    async def _enable(self, command: ParsedCommand) -> CommandResult:
        if not command.positional_args:
            return CommandResult(
                status=CommandStatus.ERROR,
                message="Usage: enable_breakpoint <id>",
                command_name=command.name,
            )
        bp_id = command.positional_args[0]
        await self._client.enable_breakpoint(bp_id)
        return CommandResult(
            status=CommandStatus.SUCCESS,
            message=f"Breakpoint {bp_id} enabled",
            command_name=command.name,
        )

    async def _disable(self, command: ParsedCommand) -> CommandResult:
        if not command.positional_args:
            return CommandResult(
                status=CommandStatus.ERROR,
                message="Usage: disable_breakpoint <id>",
                command_name=command.name,
            )
        bp_id = command.positional_args[0]
        await self._client.disable_breakpoint(bp_id)
        return CommandResult(
            status=CommandStatus.SUCCESS,
            message=f"Breakpoint {bp_id} disabled",
            command_name=command.name,
        )

    async def _list(self, command: ParsedCommand) -> CommandResult:
        bps = await self._client.list_breakpoints()
        # Update session cache
        for bp in bps:
            self._session.cache_breakpoint(bp)
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=[bp.model_dump() for bp in bps],
            message=f"{len(bps)} breakpoint(s)",
            command_name=command.name,
        )

    async def _clear(self, command: ParsedCommand) -> CommandResult:
        # Remove all cached breakpoints from Rider
        bps = self._session.breakpoints
        for bp in bps:
            try:
                await self._client.remove_breakpoint(bp.id)
            except Exception:
                pass
        count = self._session.clear_breakpoints()
        return CommandResult(
            status=CommandStatus.SUCCESS,
            message=f"Cleared {count} breakpoint(s)",
            command_name=command.name,
        )
