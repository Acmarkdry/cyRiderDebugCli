"""Unit tests for CommandRouter."""

import pytest

from rider_debug_mcp.middleware.models import (
    CommandResult,
    CommandStatus,
    ParsedCommand,
)
from rider_debug_mcp.middleware.router import BaseHandler, CommandRouter


class MockHandler(BaseHandler):
    """A mock handler that echoes the command name."""

    def __init__(self, commands: list[str]) -> None:
        self._commands = commands

    def get_commands(self) -> list[str]:
        return self._commands

    async def handle(self, command: ParsedCommand) -> CommandResult:
        return CommandResult(
            status=CommandStatus.SUCCESS,
            data={"echoed": command.name},
            message=f"Executed {command.name}",
            command_name=command.name,
        )


@pytest.fixture
def router() -> CommandRouter:
    r = CommandRouter()
    r.register(MockHandler(["add_breakpoint", "remove_breakpoint", "list_breakpoints"]))
    r.register(MockHandler(["step_over", "step_into", "step_out"]))
    return r


class TestCommandRouter:
    @pytest.mark.asyncio
    async def test_dispatch_known_command(self, router: CommandRouter):
        cmd = ParsedCommand(name="add_breakpoint", positional_args=["File.cs", "42"])
        result = await router.dispatch(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert result.data == {"echoed": "add_breakpoint"}

    @pytest.mark.asyncio
    async def test_dispatch_another_handler(self, router: CommandRouter):
        cmd = ParsedCommand(name="step_over")
        result = await router.dispatch(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert result.data == {"echoed": "step_over"}

    @pytest.mark.asyncio
    async def test_dispatch_unknown_command(self, router: CommandRouter):
        cmd = ParsedCommand(name="foo_command")
        result = await router.dispatch(cmd)
        assert result.status == CommandStatus.ERROR
        assert "Unknown command" in result.message

    @pytest.mark.asyncio
    async def test_unknown_command_suggestions(self, router: CommandRouter):
        cmd = ParsedCommand(name="add_breakpont")  # typo
        result = await router.dispatch(cmd)
        assert result.status == CommandStatus.ERROR
        assert "add_breakpoint" in result.suggestions

    def test_registered_commands(self, router: CommandRouter):
        cmds = router.registered_commands
        assert "add_breakpoint" in cmds
        assert "step_over" in cmds
        assert len(cmds) == 6

    def test_get_handler(self, router: CommandRouter):
        handler = router.get_handler("add_breakpoint")
        assert handler is not None
        assert router.get_handler("nonexistent") is None

    @pytest.mark.asyncio
    async def test_dispatch_batch(self, router: CommandRouter):
        commands = [
            ParsedCommand(name="add_breakpoint", positional_args=["F.cs", "1"]),
            ParsedCommand(name="step_over"),
        ]
        results = await router.dispatch_batch(commands)
        assert len(results) == 2
        assert all(r.status == CommandStatus.SUCCESS for r in results)

    @pytest.mark.asyncio
    async def test_dispatch_batch_stops_on_error(self, router: CommandRouter):
        commands = [
            ParsedCommand(name="add_breakpoint"),
            ParsedCommand(name="unknown_cmd"),
            ParsedCommand(name="step_over"),  # should not be reached
        ]
        results = await router.dispatch_batch(commands)
        assert len(results) == 2  # stops after error
        assert results[0].status == CommandStatus.SUCCESS
        assert results[1].status == CommandStatus.ERROR
