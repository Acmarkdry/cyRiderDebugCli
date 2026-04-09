"""Unit tests for all Pydantic data models."""

import pytest
from pydantic import ValidationError

from rider_debug_mcp.analysis.models import (
    AnnotatedStackFrame,
    CrashContext,
    CrashReport,
    ExceptionInfo,
    FrameCategory,
)
from rider_debug_mcp.gateway.events import (
    BreakpointHitEvent,
    DebugEventType,
    ExceptionEvent,
    ProcessExitEvent,
)
from rider_debug_mcp.gateway.models import (
    Breakpoint,
    BreakpointType,
    DebugSession,
    DebugSessionStatus,
    StackFrame,
    ThreadInfo,
    Variable,
)
from rider_debug_mcp.middleware.models import (
    CommandResult,
    CommandStatus,
    ErrorResult,
    ParsedCommand,
)

# === Gateway Models ===


class TestBreakpoint:
    def test_valid_breakpoint(self):
        bp = Breakpoint(id="bp-1", file="Player.cs", line=42)
        assert bp.id == "bp-1"
        assert bp.file == "Player.cs"
        assert bp.line == 42
        assert bp.enabled is True
        assert bp.condition is None
        assert bp.hit_count == 0
        assert bp.breakpoint_type == BreakpointType.LINE

    def test_conditional_breakpoint(self):
        bp = Breakpoint(
            id="bp-2",
            file="Player.cs",
            line=10,
            condition="health <= 0",
            breakpoint_type=BreakpointType.CONDITIONAL,
        )
        assert bp.condition == "health <= 0"
        assert bp.breakpoint_type == BreakpointType.CONDITIONAL

    def test_invalid_line_zero(self):
        with pytest.raises(ValidationError):
            Breakpoint(id="bp-1", file="Player.cs", line=0)

    def test_invalid_negative_hit_count(self):
        with pytest.raises(ValidationError):
            Breakpoint(id="bp-1", file="Player.cs", line=1, hit_count=-1)


class TestDebugSession:
    def test_default_session(self):
        session = DebugSession(session_id="s-1")
        assert session.status == DebugSessionStatus.NOT_STARTED
        assert session.configuration_name is None
        assert session.process_id is None

    def test_running_session(self):
        session = DebugSession(
            session_id="s-1",
            status=DebugSessionStatus.RUNNING,
            configuration_name="MyApp",
            process_id=1234,
            start_time="2025-01-01T00:00:00Z",
        )
        assert session.status == DebugSessionStatus.RUNNING
        assert session.process_id == 1234


class TestVariable:
    def test_simple_variable(self):
        var = Variable(name="health", value="100", type_name="System.Int32")
        assert var.name == "health"
        assert var.has_children is False
        assert var.children == []

    def test_variable_with_children(self):
        child = Variable(name="x", value="1.0", type_name="System.Single")
        var = Variable(
            name="position",
            value="{x=1.0, y=2.0}",
            type_name="Vector3",
            has_children=True,
            children=[child],
        )
        assert var.has_children is True
        assert len(var.children) == 1
        assert var.children[0].name == "x"


class TestStackFrame:
    def test_full_frame(self):
        frame = StackFrame(
            index=0,
            method_name="Player.TakeDamage",
            file="Player.cs",
            line=42,
            module="Assembly-CSharp",
        )
        assert frame.index == 0
        assert frame.line == 42

    def test_frame_without_source(self):
        frame = StackFrame(index=1, method_name="System.Object.ToString")
        assert frame.file is None
        assert frame.line is None


class TestThreadInfo:
    def test_main_thread(self):
        thread = ThreadInfo(thread_id=1, name="Main Thread", is_main=True)
        assert thread.is_main is True
        assert thread.state == "running"


# === Event Models ===


class TestBreakpointHitEvent:
    def test_valid_event(self):
        event = BreakpointHitEvent(
            breakpoint_id="bp-1",
            file="Player.cs",
            line=42,
            thread_id=1,
            timestamp="2025-01-01T00:00:00Z",
        )
        assert event.event_type == DebugEventType.BREAKPOINT_HIT
        assert event.breakpoint_id == "bp-1"


class TestExceptionEvent:
    def test_valid_event(self):
        event = ExceptionEvent(
            exception_type="System.NullReferenceException",
            message="Object reference not set",
            is_unhandled=True,
            thread_id=1,
            timestamp="2025-01-01T00:00:00Z",
        )
        assert event.event_type == DebugEventType.EXCEPTION
        assert event.is_unhandled is True


class TestProcessExitEvent:
    def test_normal_exit(self):
        event = ProcessExitEvent(exit_code=0, timestamp="2025-01-01T00:00:00Z")
        assert event.is_abnormal is False

    def test_abnormal_exit(self):
        event = ProcessExitEvent(exit_code=1, is_abnormal=True, timestamp="2025-01-01T00:00:00Z")
        assert event.is_abnormal is True


# === Middleware Models ===


class TestParsedCommand:
    def test_simple_command(self):
        cmd = ParsedCommand(name="add_breakpoint", positional_args=["Player.cs", "42"])
        assert cmd.name == "add_breakpoint"
        assert len(cmd.positional_args) == 2
        assert cmd.context_target is None

    def test_command_with_named_args(self):
        cmd = ParsedCommand(
            name="add_breakpoint",
            positional_args=["Player.cs", "42"],
            named_args={"condition": "health <= 0"},
        )
        assert cmd.named_args["condition"] == "health <= 0"

    def test_command_with_context(self):
        cmd = ParsedCommand(
            name="add_breakpoint",
            positional_args=["42"],
            context_target="Player.cs",
        )
        assert cmd.context_target == "Player.cs"


class TestCommandResult:
    def test_success_result(self):
        result = CommandResult(
            status=CommandStatus.SUCCESS,
            data={"id": "bp-1"},
            message="Breakpoint added",
        )
        assert result.status == CommandStatus.SUCCESS

    def test_error_result(self):
        result = ErrorResult(
            error_code="COMMAND_NOT_FOUND",
            message="Unknown command: foo",
            suggestions=["add_breakpoint", "remove_breakpoint"],
        )
        assert result.status == CommandStatus.ERROR
        assert len(result.suggestions) == 2


# === Analysis Models ===


class TestAnnotatedStackFrame:
    def test_user_code_frame(self):
        frame = AnnotatedStackFrame(
            index=0,
            namespace="MyGame.Player",
            class_name="PlayerController",
            method_name="TakeDamage",
            file="PlayerController.cs",
            line=42,
            category=FrameCategory.USER_CODE,
            is_entry_point=True,
        )
        assert frame.category == FrameCategory.USER_CODE
        assert frame.is_entry_point is True

    def test_framework_frame(self):
        frame = AnnotatedStackFrame(
            index=1,
            namespace="System",
            class_name="Object",
            method_name="ToString",
            category=FrameCategory.FRAMEWORK_CODE,
        )
        assert frame.file is None


class TestExceptionInfo:
    def test_simple_exception(self):
        exc = ExceptionInfo(
            exception_type="System.NullReferenceException",
            message="Object reference not set",
        )
        assert exc.inner_exception is None

    def test_nested_exception(self):
        inner = ExceptionInfo(
            exception_type="System.IO.FileNotFoundException",
            message="File not found",
        )
        outer = ExceptionInfo(
            exception_type="System.AggregateException",
            message="One or more errors",
            inner_exception=inner,
        )
        assert outer.inner_exception is not None
        assert outer.inner_exception.exception_type == "System.IO.FileNotFoundException"


class TestCrashContext:
    def test_full_context(self):
        ctx = CrashContext(
            exception_type="System.NullReferenceException",
            exception_message="Object reference not set",
            raw_stack_trace="at Player.TakeDamage() in Player.cs:line 42",
            timestamp="2025-01-01T00:00:00Z",
        )
        assert ctx.exception_type == "System.NullReferenceException"
        assert ctx.variables == []
        assert ctx.breakpoint_history == []

    def test_partial_context(self):
        ctx = CrashContext(
            exception_type="System.Exception",
            exception_message="Error",
            timestamp="2025-01-01T00:00:00Z",
            data_completeness={"variables": "unavailable: session not paused"},
        )
        assert ctx.data_completeness["variables"] == "unavailable: session not paused"


class TestCrashReport:
    def test_full_report(self):
        report = CrashReport(
            report_id="cr-1",
            summary="NullReferenceException in PlayerController.TakeDamage at line 42",
            investigation_suggestions=["Check null references in TakeDamage method"],
            timestamp="2025-01-01T00:00:00Z",
        )
        assert report.report_id == "cr-1"
        assert len(report.investigation_suggestions) == 1
