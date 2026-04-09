"""Command router with handler registry and fuzzy matching."""

from __future__ import annotations

import difflib
from abc import ABC, abstractmethod

from rider_debug_mcp.middleware.models import (
    CommandResult,
    CommandStatus,
    ErrorResult,
    ParsedCommand,
)


class BaseHandler(ABC):
    """Abstract base class for command handlers.

    Each handler is responsible for a set of commands in a domain
    (e.g. breakpoints, debug control, inspection).
    """

    @abstractmethod
    def get_commands(self) -> list[str]:
        """Return a list of command names this handler supports."""

    @abstractmethod
    async def handle(self, command: ParsedCommand) -> CommandResult:
        """Execute a parsed command and return a result.

        Args:
            command: The parsed command to handle.

        Returns:
            A :class:`CommandResult` with the outcome.
        """


class CommandRouter:
    """Routes parsed commands to the appropriate handler.

    Maintains a registry of ``command_name → handler`` mappings.
    When a command is unknown, returns an error with similar-command suggestions.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, BaseHandler] = {}

    def register(self, handler: BaseHandler) -> None:
        """Register a handler for all commands it supports.

        Args:
            handler: The handler instance to register.
        """
        for cmd_name in handler.get_commands():
            self._handlers[cmd_name] = handler

    @property
    def registered_commands(self) -> list[str]:
        """Return a sorted list of all registered command names."""
        return sorted(self._handlers.keys())

    def get_handler(self, command_name: str) -> BaseHandler | None:
        """Look up the handler for a given command name."""
        return self._handlers.get(command_name)

    async def dispatch(self, command: ParsedCommand) -> CommandResult:
        """Dispatch a parsed command to the appropriate handler.

        Args:
            command: The parsed command to dispatch.

        Returns:
            The result from the handler, or an :class:`ErrorResult` if the command is unknown.
        """
        handler = self.get_handler(command.name)
        if handler is not None:
            return await handler.handle(command)

        # Unknown command – try to suggest similar ones
        suggestions = difflib.get_close_matches(command.name, self._handlers.keys(), n=3, cutoff=0.5)
        return ErrorResult(
            error_code="COMMAND_NOT_FOUND",
            message=f"Unknown command: {command.name}",
            suggestions=suggestions,
            command_name=command.name,
        )

    async def dispatch_batch(self, commands: list[ParsedCommand]) -> list[CommandResult]:
        """Dispatch a batch of commands sequentially.

        Args:
            commands: The list of parsed commands to execute.

        Returns:
            A list of results, one per command.
        """
        results: list[CommandResult] = []
        for cmd in commands:
            result = await self.dispatch(cmd)
            results.append(result)
            # Stop batch on error
            if result.status == CommandStatus.ERROR:
                break
        return results
