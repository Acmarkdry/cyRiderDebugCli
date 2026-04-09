"""Unit tests for CommandParser."""

import pytest

from rider_debug_mcp.middleware.parser import CommandParser, ParseError


@pytest.fixture
def parser() -> CommandParser:
    return CommandParser()


class TestParseSingle:
    def test_simple_command(self, parser: CommandParser):
        cmd = parser.parse_single("add_breakpoint Player.cs 42")
        assert cmd.name == "add_breakpoint"
        assert cmd.positional_args == ["Player.cs", "42"]
        assert cmd.named_args == {}
        assert cmd.context_target is None

    def test_command_no_args(self, parser: CommandParser):
        cmd = parser.parse_single("list_breakpoints")
        assert cmd.name == "list_breakpoints"
        assert cmd.positional_args == []

    def test_named_args(self, parser: CommandParser):
        cmd = parser.parse_single('add_breakpoint Player.cs 42 --condition "health <= 0"')
        assert cmd.name == "add_breakpoint"
        assert cmd.positional_args == ["Player.cs", "42"]
        assert cmd.named_args == {"condition": "health <= 0"}

    def test_multiple_named_args(self, parser: CommandParser):
        cmd = parser.parse_single("start_debug --config MyApp --mode release")
        assert cmd.named_args == {"config": "MyApp", "mode": "release"}

    def test_context_target(self, parser: CommandParser):
        cmd = parser.parse_single("add_breakpoint 42", context_target="Player.cs")
        assert cmd.name == "add_breakpoint"
        assert cmd.positional_args == ["42"]
        assert cmd.context_target == "Player.cs"

    def test_preserves_raw(self, parser: CommandParser):
        raw = "add_breakpoint Player.cs 42"
        cmd = parser.parse_single(raw)
        assert cmd.raw == raw

    def test_empty_command_raises(self, parser: CommandParser):
        with pytest.raises(ParseError):
            parser.parse_single("")

    def test_whitespace_only_raises(self, parser: CommandParser):
        with pytest.raises(ParseError):
            parser.parse_single("   ")

    def test_named_arg_missing_value_raises(self, parser: CommandParser):
        with pytest.raises(ParseError, match="missing value"):
            parser.parse_single("add_breakpoint --condition")

    def test_empty_named_key_raises(self, parser: CommandParser):
        with pytest.raises(ParseError, match="Empty named argument"):
            parser.parse_single("add_breakpoint -- foo")

    def test_quoted_arg_with_spaces(self, parser: CommandParser):
        cmd = parser.parse_single('evaluate "player.Health + 10"')
        assert cmd.name == "evaluate"
        assert cmd.positional_args == ["player.Health + 10"]


class TestParseBatch:
    def test_single_command_batch(self, parser: CommandParser):
        commands = parser.parse_batch("add_breakpoint Player.cs 42")
        assert len(commands) == 1
        assert commands[0].name == "add_breakpoint"

    def test_multi_command_batch(self, parser: CommandParser):
        text = "add_breakpoint File.cs 10\nadd_breakpoint File.cs 20\nlist_breakpoints"
        commands = parser.parse_batch(text)
        assert len(commands) == 3
        assert commands[0].positional_args == ["File.cs", "10"]
        assert commands[1].positional_args == ["File.cs", "20"]
        assert commands[2].name == "list_breakpoints"

    def test_comments_ignored(self, parser: CommandParser):
        text = "# Set breakpoints\nadd_breakpoint File.cs 10\n# Done"
        commands = parser.parse_batch(text)
        assert len(commands) == 1
        assert commands[0].name == "add_breakpoint"

    def test_context_target(self, parser: CommandParser):
        text = "@PlayerController.cs\nadd_breakpoint 42\nadd_breakpoint 55"
        commands = parser.parse_batch(text)
        assert len(commands) == 2
        assert commands[0].context_target == "PlayerController.cs"
        assert commands[0].positional_args == ["42"]
        assert commands[1].context_target == "PlayerController.cs"
        assert commands[1].positional_args == ["55"]

    def test_context_target_changes(self, parser: CommandParser):
        text = "@File1.cs\nadd_breakpoint 10\n@File2.cs\nadd_breakpoint 20"
        commands = parser.parse_batch(text)
        assert commands[0].context_target == "File1.cs"
        assert commands[1].context_target == "File2.cs"

    def test_blank_lines_skipped(self, parser: CommandParser):
        text = "\nadd_breakpoint File.cs 10\n\nlist_breakpoints\n"
        commands = parser.parse_batch(text)
        assert len(commands) == 2

    def test_empty_input_raises(self, parser: CommandParser):
        with pytest.raises(ParseError):
            parser.parse_batch("")

    def test_only_comments_raises(self, parser: CommandParser):
        with pytest.raises(ParseError, match="No executable commands"):
            parser.parse_batch("# just a comment\n# another comment")

    def test_empty_context_target_raises(self, parser: CommandParser):
        with pytest.raises(ParseError, match="Empty context target"):
            parser.parse_batch("@\nadd_breakpoint 42")

    def test_preserves_order(self, parser: CommandParser):
        text = "step_over\nstep_into\nstep_out"
        commands = parser.parse_batch(text)
        assert [c.name for c in commands] == ["step_over", "step_into", "step_out"]

    def test_complex_batch(self, parser: CommandParser):
        text = (
            "# Debug session setup\n"
            "@PlayerController.cs\n"
            "add_breakpoint 42\n"
            'add_breakpoint 55 --condition "health <= 0"\n'
            "\n"
            "# Start debugging\n"
            "start_debug\n"
        )
        commands = parser.parse_batch(text)
        assert len(commands) == 3
        assert commands[0].name == "add_breakpoint"
        assert commands[0].context_target == "PlayerController.cs"
        assert commands[1].named_args == {"condition": "health <= 0"}
        assert commands[2].name == "start_debug"
        assert commands[2].context_target == "PlayerController.cs"
