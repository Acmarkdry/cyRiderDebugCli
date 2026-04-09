"""Shared test fixtures and factories."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rider_debug_mcp.gateway.client import RiderClient
from rider_debug_mcp.gateway.models import (
    Breakpoint,
    DebugSession,
    DebugSessionStatus,
    StackFrame,
    ThreadInfo,
    Variable,
)
from rider_debug_mcp.middleware.session import SessionManager

# --- Factories ---


def make_breakpoint(**overrides) -> Breakpoint:
    defaults = {"id": "bp-1", "file": "Player.cs", "line": 42}
    defaults.update(overrides)
    return Breakpoint(**defaults)


def make_variable(**overrides) -> Variable:
    defaults = {"name": "health", "value": "100", "type_name": "System.Int32"}
    defaults.update(overrides)
    return Variable(**defaults)


def make_stack_frame(**overrides) -> StackFrame:
    defaults = {"index": 0, "method_name": "Player.TakeDamage", "file": "Player.cs", "line": 42}
    defaults.update(overrides)
    return StackFrame(**defaults)


def make_thread(**overrides) -> ThreadInfo:
    defaults = {"thread_id": 1, "name": "Main Thread", "is_main": True}
    defaults.update(overrides)
    return ThreadInfo(**defaults)


# --- Fixtures ---


@pytest.fixture
def mock_rider_client() -> RiderClient:
    """A fully mocked RiderClient."""
    client = MagicMock(spec=RiderClient)
    client.add_breakpoint = AsyncMock(return_value=make_breakpoint())
    client.remove_breakpoint = AsyncMock(return_value=True)
    client.enable_breakpoint = AsyncMock(return_value=True)
    client.disable_breakpoint = AsyncMock(return_value=True)
    client.list_breakpoints = AsyncMock(return_value=[make_breakpoint()])
    client.start_debug = AsyncMock(
        return_value=DebugSession(session_id="s-1", status=DebugSessionStatus.RUNNING)
    )
    client.stop_debug = AsyncMock(return_value=True)
    client.pause = AsyncMock(return_value=True)
    client.resume = AsyncMock(return_value=True)
    client.step_over = AsyncMock(return_value={"file": "Player.cs", "line": 43})
    client.step_into = AsyncMock(return_value={"file": "Player.cs", "line": 10})
    client.step_out = AsyncMock(return_value={"file": "Player.cs", "line": 50})
    client.get_variables = AsyncMock(return_value=[make_variable()])
    client.evaluate_expression = AsyncMock(return_value={"result": "100", "type": "Int32"})
    client.get_stack_trace = AsyncMock(return_value=[make_stack_frame()])
    client.get_threads = AsyncMock(return_value=[make_thread()])
    client.health_check = AsyncMock(return_value={"connected": True, "port": 63342})
    return client


@pytest.fixture
def session_manager() -> SessionManager:
    """A fresh SessionManager instance."""
    return SessionManager()
