"""Pydantic data models for Rider Gateway communication."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class BreakpointType(str, Enum):
    """Type of breakpoint."""

    LINE = "line"
    CONDITIONAL = "conditional"
    EXCEPTION = "exception"


class Breakpoint(BaseModel):
    """Represents a debugger breakpoint."""

    id: str = Field(description="Unique breakpoint identifier")
    file: str = Field(description="Source file path")
    line: int = Field(ge=1, description="Line number (1-based)")
    enabled: bool = Field(default=True, description="Whether the breakpoint is active")
    condition: str | None = Field(default=None, description="Optional condition expression")
    hit_count: int = Field(default=0, ge=0, description="Number of times the breakpoint was hit")
    breakpoint_type: BreakpointType = Field(default=BreakpointType.LINE, description="Breakpoint type")


class DebugSessionStatus(str, Enum):
    """Status of a debug session."""

    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    NOT_STARTED = "not_started"


class DebugSession(BaseModel):
    """Represents an active debug session."""

    session_id: str = Field(description="Unique session identifier")
    status: DebugSessionStatus = Field(default=DebugSessionStatus.NOT_STARTED, description="Current session status")
    configuration_name: str | None = Field(default=None, description="Run configuration name")
    process_id: int | None = Field(default=None, description="Debugged process ID")
    start_time: str | None = Field(default=None, description="Session start time (ISO 8601)")


class Variable(BaseModel):
    """Represents a runtime variable."""

    name: str = Field(description="Variable name")
    value: str = Field(description="String representation of the value")
    type_name: str = Field(description="Type name of the variable")
    has_children: bool = Field(default=False, description="Whether the variable has child members")
    children: list[Variable] = Field(default_factory=list, description="Child variables (if expanded)")


class StackFrame(BaseModel):
    """Represents a single stack frame."""

    index: int = Field(ge=0, description="Frame index (0 = top)")
    method_name: str = Field(description="Fully qualified method name")
    file: str | None = Field(default=None, description="Source file path")
    line: int | None = Field(default=None, ge=1, description="Line number in source file")
    module: str | None = Field(default=None, description="Module/assembly name")


class ThreadInfo(BaseModel):
    """Represents a debugger thread."""

    thread_id: int = Field(description="Thread ID")
    name: str | None = Field(default=None, description="Thread name")
    state: str = Field(default="running", description="Thread state (running, suspended, etc.)")
    is_main: bool = Field(default=False, description="Whether this is the main thread")
    stack_frames: list[StackFrame] = Field(default_factory=list, description="Stack frames for this thread")
