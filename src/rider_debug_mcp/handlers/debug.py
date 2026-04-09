"""Debug control command handler."""

from __future__ import annotations

from rider_debug_mcp.gateway.client import RiderClient
from rider_debug_mcp.middleware.models import CommandResult, CommandStatus, ParsedCommand
from rider_debug_mcp.middleware.router import BaseHandler
from rider_debug_mcp.middleware.session import SessionManager


class DebugHandler(BaseHandler):
    """Handles debug control commands (start, stop, step, etc.)."""

    def __init__(self, client: RiderClient, session: SessionManager) -> None:
        self._client = client
        self._session = session

    def get_commands(self) -> list[str]:
        return ["start_debug", "stop_debug", "pause", "resume", "step_over", "step_into", "step_out"]

    async def handle(self, command: ParsedCommand) -> CommandResult:
        handler_map = {
            "start_debug": self._start,
            "stop_debug": self._stop,
            "pause": self._pause,
            "resume": self._resume,
            "step_over": self._step_over,
            "step_into": self._step_into,
            "step_out": self._step_out,
        }
        handler_fn = handler_map[command.name]
        return await handler_fn(command)

    async def _start(self, command: ParsedCommand) -> CommandResult:
        config_name = command.positional_args[0] if command.positional_args else command.named_args.get("config")
        debug_session = await self._client.start_debug(config_name)
        self._session.start_session(config_name)
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=debug_session.model_dump(),
            message=f"Debug session started (ID: {debug_session.session_id})",
            command_name=command.name,
        )

    async def _stop(self, command: ParsedCommand) -> CommandResult:
        await self._client.stop_debug()
        self._session.stop_session()
        return CommandResult(
            status=CommandStatus.SUCCESS,
            message="Debug session stopped",
            command_name=command.name,
        )

    async def _pause(self, command: ParsedCommand) -> CommandResult:
        await self._client.pause()
        self._session.pause_session()
        return CommandResult(
            status=CommandStatus.SUCCESS,
            message="Execution paused",
            command_name=command.name,
        )

    async def _resume(self, command: ParsedCommand) -> CommandResult:
        await self._client.resume()
        self._session.resume_session()
        return CommandResult(
            status=CommandStatus.SUCCESS,
            message="Execution resumed",
            command_name=command.name,
        )

    async def _step_over(self, command: ParsedCommand) -> CommandResult:
        data = await self._client.step_over()
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=data,
            message="Stepped over",
            command_name=command.name,
        )

    async def _step_into(self, command: ParsedCommand) -> CommandResult:
        data = await self._client.step_into()
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=data,
            message="Stepped into",
            command_name=command.name,
        )

    async def _step_out(self, command: ParsedCommand) -> CommandResult:
        data = await self._client.step_out()
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=data,
            message="Stepped out",
            command_name=command.name,
        )
