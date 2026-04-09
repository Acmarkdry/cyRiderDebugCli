"""Data models for crash analysis."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from rider_debug_mcp.gateway.models import Variable


class FrameCategory(str, Enum):
    """Category of a stack frame."""

    USER_CODE = "user_code"
    FRAMEWORK_CODE = "framework_code"
    UNKNOWN = "unknown"


class AnnotatedStackFrame(BaseModel):
    """Stack frame with analysis annotations."""

    index: int = Field(ge=0, description="Frame index (0 = top)")
    namespace: str | None = Field(default=None, description="Namespace of the class")
    class_name: str | None = Field(default=None, description="Class name")
    method_name: str = Field(description="Method name")
    file: str | None = Field(default=None, description="Source file path")
    line: int | None = Field(default=None, ge=1, description="Line number")
    category: FrameCategory = Field(default=FrameCategory.UNKNOWN, description="User code vs framework code")
    is_entry_point: bool = Field(default=False, description="Whether this frame is the likely crash entry point")


class ExceptionInfo(BaseModel):
    """Structured exception information."""

    exception_type: str = Field(description="Fully qualified exception type")
    message: str = Field(description="Exception message")
    inner_exception: ExceptionInfo | None = Field(default=None, description="Inner/cause exception")


class CrashContext(BaseModel):
    """Context collected when a crash is detected."""

    exception_type: str = Field(description="Exception type name")
    exception_message: str = Field(description="Exception message")
    raw_stack_trace: str | None = Field(default=None, description="Raw stack trace text")
    annotated_frames: list[AnnotatedStackFrame] = Field(default_factory=list, description="Parsed and annotated frames")
    variables: list[Variable] = Field(default_factory=list, description="Variables at crash point")
    thread_id: int | None = Field(default=None, description="Thread where crash occurred")
    breakpoint_history: list[str] = Field(
        default_factory=list, description="Recent breakpoint hit IDs before crash"
    )
    timestamp: str = Field(description="Crash timestamp (ISO 8601)")
    data_completeness: dict[str, str] = Field(
        default_factory=dict,
        description="Tracks which data was collected vs unavailable (field -> 'collected' | reason)",
    )


class CrashReport(BaseModel):
    """Structured crash analysis report."""

    report_id: str = Field(description="Unique report identifier")
    summary: str = Field(description="1-2 sentence crash summary")
    exception_chain: list[ExceptionInfo] = Field(default_factory=list, description="Exception chain (outer to inner)")
    annotated_stack: list[AnnotatedStackFrame] = Field(default_factory=list, description="Annotated stack trace")
    variable_snapshot: list[Variable] = Field(default_factory=list, description="Variables at crash point")
    investigation_suggestions: list[str] = Field(
        default_factory=list, description="Suggested next steps for investigation"
    )
    timestamp: str = Field(description="Report generation timestamp (ISO 8601)")
    crash_context: CrashContext | None = Field(default=None, description="Original crash context")
