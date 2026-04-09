"""Inspection command handler for variables, stack traces, and threads."""

from __future__ import annotations

from rider_debug_mcp.gateway.client import RiderClient
from rider_debug_mcp.middleware.models import CommandResult, CommandStatus, ParsedCommand
from rider_debug_mcp.middleware.router import BaseHandler


class InspectHandler(BaseHandler):
    """Handles runtime inspection commands."""

    def __init__(self, client: RiderClient) -> None:
        self._client = client

    def get_commands(self) -> list[str]:
        return ["get_variables", "evaluate", "get_stack_trace", "get_threads"]

    async def handle(self, command: ParsedCommand) -> CommandResult:
        handler_map = {
            "get_variables": self._get_variables,
            "evaluate": self._evaluate,
            "get_stack_trace": self._get_stack_trace,
            "get_threads": self._get_threads,
        }
        handler_fn = handler_map[command.name]
        return await handler_fn(command)

    async def _get_variables(self, command: ParsedCommand) -> CommandResult:
        frame_index = 0
        if command.positional_args:
            try:
                frame_index = int(command.positional_args[0])
            except ValueError:
                pass
        variables = await self._client.get_variables(frame_index)
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=[v.model_dump() for v in variables],
            message=f"{len(variables)} variable(s) in frame {frame_index}",
            command_name=command.name,
        )

    async def _evaluate(self, command: ParsedCommand) -> CommandResult:
        if not command.positional_args:
            return CommandResult(
                status=CommandStatus.ERROR,
                message="Usage: evaluate <expression>",
                command_name=command.name,
            )
        expression = " ".join(command.positional_args)
        result = await self._client.evaluate_expression(expression)
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=result,
            message=f"Evaluated: {expression}",
            command_name=command.name,
        )

    async def _get_stack_trace(self, command: ParsedCommand) -> CommandResult:
        thread_id = None
        if command.positional_args:
            try:
                thread_id = int(command.positional_args[0])
            except ValueError:
                pass
        frames = await self._client.get_stack_trace(thread_id)
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=[f.model_dump() for f in frames],
            message=f"{len(frames)} frame(s) in stack trace",
            command_name=command.name,
        )

    async def _get_threads(self, command: ParsedCommand) -> CommandResult:
        threads = await self._client.get_threads()
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data=[t.model_dump() for t in threads],
            message=f"{len(threads)} thread(s)",
            command_name=command.name,
        )
