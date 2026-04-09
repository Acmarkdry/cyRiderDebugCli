"""Command parser for CLI syntax."""

from __future__ import annotations

import shlex

from rider_debug_mcp.middleware.models import ParsedCommand


class ParseError(Exception):
    """Raised when a command string cannot be parsed."""

    def __init__(self, message: str, line: str | None = None, line_number: int | None = None) -> None:
        self.line = line
        self.line_number = line_number
        detail = message
        if line_number is not None:
            detail = f"Line {line_number}: {detail}"
        if line is not None:
            detail = f"{detail} (input: {line!r})"
        super().__init__(detail)


class CommandParser:
    """Parses CLI command strings into structured ParsedCommand objects.

    Supports:
    - Positional arguments: ``add_breakpoint Player.cs 42``
    - Named arguments: ``--key value``
    - Context targets: ``@PlayerController.cs``
    - Comments: ``# this is a comment``
    - Multi-line batch parsing
    """

    def parse_single(self, raw: str, context_target: str | None = None) -> ParsedCommand:
        """Parse a single command line.

        Args:
            raw: The raw command string.
            context_target: An inherited context target from a preceding ``@target`` line.

        Returns:
            A :class:`ParsedCommand` instance.

        Raises:
            ParseError: If the command string is empty or malformed.
        """
        stripped = raw.strip()
        if not stripped:
            raise ParseError("Empty command", line=raw)

        try:
            tokens = shlex.split(stripped)
        except ValueError as exc:
            raise ParseError(f"Malformed command: {exc}", line=raw) from exc

        if not tokens:
            raise ParseError("Empty command after tokenisation", line=raw)

        command_name = tokens[0]
        positional_args: list[str] = []
        named_args: dict[str, str] = {}

        i = 1
        while i < len(tokens):
            token = tokens[i]
            if token.startswith("--"):
                key = token[2:]
                if not key:
                    raise ParseError("Empty named argument key '--'", line=raw)
                if i + 1 < len(tokens):
                    named_args[key] = tokens[i + 1]
                    i += 2
                else:
                    raise ParseError(f"Named argument '--{key}' missing value", line=raw)
            else:
                positional_args.append(token)
                i += 1

        return ParsedCommand(
            name=command_name,
            positional_args=positional_args,
            named_args=named_args,
            context_target=context_target,
            raw=raw,
        )

    def parse_batch(self, text: str) -> list[ParsedCommand]:
        """Parse a multi-line batch of commands.

        - Lines starting with ``#`` are treated as comments and skipped.
        - Lines starting with ``@`` set the context target for subsequent commands.
        - Blank lines are skipped.

        Args:
            text: The full multi-line command text.

        Returns:
            A list of :class:`ParsedCommand` instances, preserving order.

        Raises:
            ParseError: If the batch has no executable commands or a line is malformed.
        """
        if not text or not text.strip():
            raise ParseError("Empty command input")

        lines = text.splitlines()
        commands: list[ParsedCommand] = []
        context_target: str | None = None

        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Skip blank lines
            if not stripped:
                continue

            # Skip comments
            if stripped.startswith("#"):
                continue

            # Context target
            if stripped.startswith("@"):
                target = stripped[1:].strip()
                if not target:
                    raise ParseError("Empty context target '@'", line=line, line_number=line_no)
                context_target = target
                continue

            # Regular command
            try:
                cmd = self.parse_single(stripped, context_target=context_target)
                commands.append(cmd)
            except ParseError as exc:
                raise ParseError(str(exc), line=line, line_number=line_no) from exc

        if not commands:
            raise ParseError("No executable commands found in batch input")

        return commands
