"""Middleware data models for command parsing and response formatting."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ParsedCommand(BaseModel):
    """Represents a parsed CLI command."""

    name: str = Field(description="Command name (e.g., 'add_breakpoint')")
    positional_args: list[str] = Field(default_factory=list, description="Positional arguments")
    named_args: dict[str, str] = Field(default_factory=dict, description="Named arguments (--key value)")
    context_target: str | None = Field(default=None, description="Context target from @target syntax")
    raw: str = Field(default="", description="Original raw command string")


class CommandStatus(str, Enum):
    """Status of a command execution."""

    SUCCESS = "success"
    ERROR = "error"


class CommandResult(BaseModel):
    """Result of a command execution."""

    status: CommandStatus = Field(description="Execution status")
    data: Any = Field(default=None, description="Result data payload")
    message: str | None = Field(default=None, description="Human-readable summary message")
    command_name: str | None = Field(default=None, description="Name of the command that was executed")


class ErrorResult(BaseModel):
    """Detailed error result for failed commands."""

    status: CommandStatus = Field(default=CommandStatus.ERROR, description="Always 'error'")
    error_code: str = Field(description="Error code identifier")
    message: str = Field(description="Descriptive error message")
    suggestions: list[str] = Field(default_factory=list, description="Suggested fixes or alternative commands")
    command_name: str | None = Field(default=None, description="Name of the command that failed")
