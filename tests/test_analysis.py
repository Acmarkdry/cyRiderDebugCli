"""Unit tests for CrashAnalyzer and ReportGenerator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rider_debug_mcp.analysis.crash import CrashAnalyzer, parse_dotnet_stack_trace
from rider_debug_mcp.analysis.models import FrameCategory
from rider_debug_mcp.analysis.report import ReportGenerator
from rider_debug_mcp.gateway.events import ExceptionEvent, ProcessExitEvent
from rider_debug_mcp.gateway.models import Variable
from rider_debug_mcp.middleware.session import SessionManager

SAMPLE_STACK_TRACE = """\
   at MyGame.Player.PlayerController.TakeDamage(Int32 amount) in C:\\Projects\\MyGame\\PlayerController.cs:line 42
   at MyGame.Combat.CombatSystem.ApplyDamage(Player target) in C:\\Projects\\MyGame\\CombatSystem.cs:line 88
   at System.Runtime.CompilerServices.TaskAwaiter.HandleNonSuccessAndDebuggerNotification(Task task)
   at UnityEngine.MonoBehaviour.Update()
"""


class TestParseDotnetStackTrace:
    def test_parse_basic(self):
        frames = parse_dotnet_stack_trace(SAMPLE_STACK_TRACE)
        assert len(frames) == 4

    def test_user_code_detection(self):
        frames = parse_dotnet_stack_trace(SAMPLE_STACK_TRACE)
        # First two are user code (MyGame namespace)
        assert frames[0].category == FrameCategory.USER_CODE
        assert frames[1].category == FrameCategory.USER_CODE
        # System and UnityEngine are framework
        assert frames[2].category == FrameCategory.FRAMEWORK_CODE
        assert frames[3].category == FrameCategory.FRAMEWORK_CODE

    def test_entry_point(self):
        frames = parse_dotnet_stack_trace(SAMPLE_STACK_TRACE)
        assert frames[0].is_entry_point is True
        assert frames[1].is_entry_point is False

    def test_parsed_details(self):
        frames = parse_dotnet_stack_trace(SAMPLE_STACK_TRACE)
        f0 = frames[0]
        assert f0.namespace == "MyGame.Player"
        assert f0.class_name == "PlayerController"
        assert f0.method_name == "TakeDamage"
        assert f0.file == "C:\\Projects\\MyGame\\PlayerController.cs"
        assert f0.line == 42

    def test_frame_without_file(self):
        frames = parse_dotnet_stack_trace(SAMPLE_STACK_TRACE)
        # System frame has no file info
        f2 = frames[2]
        assert f2.file is None
        assert f2.line is None

    def test_custom_user_patterns(self):
        frames = parse_dotnet_stack_trace(
            SAMPLE_STACK_TRACE,
            user_namespace_patterns=["MyGame.Player"],
        )
        assert frames[0].category == FrameCategory.USER_CODE
        # MyGame.Combat doesn't match the pattern
        assert frames[1].category == FrameCategory.FRAMEWORK_CODE

    def test_empty_trace(self):
        frames = parse_dotnet_stack_trace("")
        assert frames == []


class TestReportGenerator:
    def test_generate_report(self):
        from rider_debug_mcp.analysis.models import CrashContext

        frames = parse_dotnet_stack_trace(SAMPLE_STACK_TRACE)
        ctx = CrashContext(
            exception_type="System.NullReferenceException",
            exception_message="Object reference not set",
            raw_stack_trace=SAMPLE_STACK_TRACE,
            annotated_frames=frames,
            timestamp="2025-01-01T00:00:00Z",
        )

        gen = ReportGenerator()
        report = gen.generate(ctx)

        assert report.report_id.startswith("cr-")
        assert "NullReferenceException" in report.summary
        assert "PlayerController" in report.summary
        assert len(report.exception_chain) == 1
        assert len(report.annotated_stack) == 4
        assert len(report.investigation_suggestions) > 0

    def test_null_reference_suggestions(self):
        from rider_debug_mcp.analysis.models import CrashContext

        frames = parse_dotnet_stack_trace(SAMPLE_STACK_TRACE)
        ctx = CrashContext(
            exception_type="System.NullReferenceException",
            exception_message="Object reference not set",
            annotated_frames=frames,
            timestamp="2025-01-01T00:00:00Z",
        )
        gen = ReportGenerator()
        report = gen.generate(ctx)
        assert any("null" in s.lower() for s in report.investigation_suggestions)

    def test_report_without_stack(self):
        from rider_debug_mcp.analysis.models import CrashContext

        ctx = CrashContext(
            exception_type="ProcessExit",
            exception_message="Process exited with code 1",
            timestamp="2025-01-01T00:00:00Z",
        )
        gen = ReportGenerator()
        report = gen.generate(ctx)
        assert report.summary == "ProcessExit: Process exited with code 1"
        assert len(report.annotated_stack) == 0


class TestCrashAnalyzer:
    @pytest.fixture
    def setup(self):
        client = MagicMock()
        client.get_variables = AsyncMock(
            return_value=[Variable(name="health", value="0", type_name="Int32")]
        )
        session = SessionManager()
        report_gen = ReportGenerator()
        analyzer = CrashAnalyzer(client, session, report_gen)
        return analyzer, client, session

    @pytest.mark.asyncio
    async def test_on_exception(self, setup):
        analyzer, _, _ = setup
        event = ExceptionEvent(
            exception_type="System.NullReferenceException",
            message="Object reference not set",
            stack_trace=SAMPLE_STACK_TRACE,
            is_unhandled=True,
            thread_id=1,
            timestamp="2025-01-01T00:00:00Z",
        )
        await analyzer.on_exception(event)
        assert len(analyzer.get_history()) == 1
        report = analyzer.get_latest_report()
        assert report is not None
        assert "NullReferenceException" in report.summary

    @pytest.mark.asyncio
    async def test_on_process_exit_normal(self, setup):
        analyzer, _, _ = setup
        event = ProcessExitEvent(exit_code=0, is_abnormal=False, timestamp="2025-01-01T00:00:00Z")
        await analyzer.on_process_exit(event)
        assert len(analyzer.get_history()) == 0  # normal exit, no report

    @pytest.mark.asyncio
    async def test_on_process_exit_abnormal(self, setup):
        analyzer, _, _ = setup
        event = ProcessExitEvent(exit_code=1, is_abnormal=True, timestamp="2025-01-01T00:00:00Z")
        await analyzer.on_process_exit(event)
        assert len(analyzer.get_history()) == 1

    @pytest.mark.asyncio
    async def test_analyze_latest_no_crash(self, setup):
        analyzer, _, _ = setup
        result = await analyzer.analyze_latest()
        assert result is None

    @pytest.mark.asyncio
    async def test_clear_history(self, setup):
        analyzer, _, _ = setup
        event = ExceptionEvent(
            exception_type="System.Exception",
            message="Test",
            thread_id=1,
            timestamp="2025-01-01T00:00:00Z",
        )
        await analyzer.on_exception(event)
        assert len(analyzer.get_history()) == 1
        analyzer.clear_history()
        assert len(analyzer.get_history()) == 0
