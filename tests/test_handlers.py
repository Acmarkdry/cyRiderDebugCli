"""Unit tests for all command handlers (mocked gateway)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rider_debug_mcp.analysis.crash import CrashAnalyzer
from rider_debug_mcp.analysis.report import ReportGenerator
from rider_debug_mcp.gateway.client import RiderClient
from rider_debug_mcp.gateway.models import (
    Breakpoint,
    DebugSession,
    DebugSessionStatus,
    StackFrame,
    ThreadInfo,
    Variable,
)
from rider_debug_mcp.handlers.analysis import AnalysisHandler
from rider_debug_mcp.handlers.breakpoint import BreakpointHandler
from rider_debug_mcp.handlers.debug import DebugHandler
from rider_debug_mcp.handlers.inspect import InspectHandler
from rider_debug_mcp.middleware.models import CommandStatus, ParsedCommand
from rider_debug_mcp.middleware.session import SessionManager


@pytest.fixture
def mock_client() -> RiderClient:
    client = MagicMock(spec=RiderClient)
    # Breakpoint methods
    client.add_breakpoint = AsyncMock(
        return_value=Breakpoint(id="bp-1", file="Player.cs", line=42)
    )
    client.remove_breakpoint = AsyncMock(return_value=True)
    client.enable_breakpoint = AsyncMock(return_value=True)
    client.disable_breakpoint = AsyncMock(return_value=True)
    client.list_breakpoints = AsyncMock(
        return_value=[Breakpoint(id="bp-1", file="Player.cs", line=42)]
    )
    # Debug methods
    client.start_debug = AsyncMock(
        return_value=DebugSession(session_id="s-1", status=DebugSessionStatus.RUNNING)
    )
    client.stop_debug = AsyncMock(return_value=True)
    client.pause = AsyncMock(return_value=True)
    client.resume = AsyncMock(return_value=True)
    client.step_over = AsyncMock(return_value={"file": "P.cs", "line": 43})
    client.step_into = AsyncMock(return_value={"file": "P.cs", "line": 10})
    client.step_out = AsyncMock(return_value={"file": "P.cs", "line": 50})
    # Inspect methods
    client.get_variables = AsyncMock(
        return_value=[Variable(name="health", value="100", type_name="Int32")]
    )
    client.evaluate_expression = AsyncMock(return_value={"result": "100", "type": "Int32"})
    client.get_stack_trace = AsyncMock(
        return_value=[StackFrame(index=0, method_name="Player.TakeDamage", file="P.cs", line=42)]
    )
    client.get_threads = AsyncMock(
        return_value=[ThreadInfo(thread_id=1, name="Main", is_main=True)]
    )
    return client


@pytest.fixture
def session() -> SessionManager:
    return SessionManager()


# === Breakpoint Handler ===


class TestBreakpointHandler:
    @pytest.mark.asyncio
    async def test_add_breakpoint(self, mock_client, session):
        handler = BreakpointHandler(mock_client, session)
        cmd = ParsedCommand(name="add_breakpoint", positional_args=["Player.cs", "42"])
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert session.breakpoint_count == 1

    @pytest.mark.asyncio
    async def test_add_breakpoint_with_context(self, mock_client, session):
        handler = BreakpointHandler(mock_client, session)
        cmd = ParsedCommand(name="add_breakpoint", positional_args=["42"], context_target="Player.cs")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_add_breakpoint_missing_args(self, mock_client, session):
        handler = BreakpointHandler(mock_client, session)
        cmd = ParsedCommand(name="add_breakpoint", positional_args=["Player.cs"])
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.ERROR

    @pytest.mark.asyncio
    async def test_remove_breakpoint(self, mock_client, session):
        handler = BreakpointHandler(mock_client, session)
        cmd = ParsedCommand(name="remove_breakpoint", positional_args=["bp-1"])
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_list_breakpoints(self, mock_client, session):
        handler = BreakpointHandler(mock_client, session)
        cmd = ParsedCommand(name="list_breakpoints")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert len(result.data) == 1

    @pytest.mark.asyncio
    async def test_clear_breakpoints(self, mock_client, session):
        handler = BreakpointHandler(mock_client, session)
        session.cache_breakpoint(Breakpoint(id="bp-1", file="P.cs", line=1))
        cmd = ParsedCommand(name="clear_breakpoints")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert session.breakpoint_count == 0


# === Debug Handler ===


class TestDebugHandler:
    @pytest.mark.asyncio
    async def test_start_debug(self, mock_client, session):
        handler = DebugHandler(mock_client, session)
        cmd = ParsedCommand(name="start_debug", positional_args=["MyApp"])
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert session.is_active

    @pytest.mark.asyncio
    async def test_stop_debug(self, mock_client, session):
        handler = DebugHandler(mock_client, session)
        session.start_session()
        cmd = ParsedCommand(name="stop_debug")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_step_over(self, mock_client, session):
        handler = DebugHandler(mock_client, session)
        cmd = ParsedCommand(name="step_over")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert result.data["line"] == 43


# === Inspect Handler ===


class TestInspectHandler:
    @pytest.mark.asyncio
    async def test_get_variables(self, mock_client):
        handler = InspectHandler(mock_client)
        cmd = ParsedCommand(name="get_variables")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert len(result.data) == 1

    @pytest.mark.asyncio
    async def test_evaluate(self, mock_client):
        handler = InspectHandler(mock_client)
        cmd = ParsedCommand(name="evaluate", positional_args=["player.Health"])
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_evaluate_missing_expr(self, mock_client):
        handler = InspectHandler(mock_client)
        cmd = ParsedCommand(name="evaluate")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.ERROR

    @pytest.mark.asyncio
    async def test_get_stack_trace(self, mock_client):
        handler = InspectHandler(mock_client)
        cmd = ParsedCommand(name="get_stack_trace")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_get_threads(self, mock_client):
        handler = InspectHandler(mock_client)
        cmd = ParsedCommand(name="get_threads")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert len(result.data) == 1


# === Analysis Handler ===


class TestAnalysisHandler:
    @pytest.mark.asyncio
    async def test_crash_report_empty(self, mock_client, session):
        report_gen = ReportGenerator()
        analyzer = CrashAnalyzer(mock_client, session, report_gen)
        handler = AnalysisHandler(analyzer)
        cmd = ParsedCommand(name="crash_report")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert "No crash reports" in result.message

    @pytest.mark.asyncio
    async def test_crash_history_empty(self, mock_client, session):
        report_gen = ReportGenerator()
        analyzer = CrashAnalyzer(mock_client, session, report_gen)
        handler = AnalysisHandler(analyzer)
        cmd = ParsedCommand(name="crash_history")
        result = await handler.handle(cmd)
        assert result.status == CommandStatus.SUCCESS
        assert len(result.data) == 0
