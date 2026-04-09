"""Unit tests for RiderClient (mocked HTTP responses)."""

import json

import httpx
import pytest

from rider_debug_mcp.gateway.client import RiderClient, RiderConnectionError
from rider_debug_mcp.gateway.models import DebugSessionStatus


def _mock_transport(responses: dict[str, httpx.Response | None] | None = None) -> httpx.MockTransport:
    """Create a mock transport for native JetBrains HTTP server endpoints.

    Routes:
      GET  /api/about                               → IDE identity
      GET  /api/file                                 → open file (used by breakpoints)
      POST /api/internal/executeAction/{actionId}    → trigger action
      POST /api/internal/runScript                   → Groovy script execution
    """
    custom = responses or {}

    # Pre-built Groovy script responses keyed by a recognizable substring
    _script_responses = {
        "allBreakpoints": json.dumps({
            "breakpoints": [
                {"id": "bp-Player.cs:42", "file": "Player.cs", "line": 42, "enabled": True},
            ]
        }),
        "XValue enumeration": json.dumps({
            "variables": [
                {"name": "health", "value": "100", "type": "System.Int32", "hasChildren": False},
            ],
            "frame": {"file": "Player.cs", "line": 42},
        }),
        "evaluationExpression": json.dumps({
            "frames": [
                {"method": "Player.TakeDamage", "file": "Player.cs", "line": 42, "module": "Assembly-CSharp"},
            ]
        }),
        "activeExecutionStack": json.dumps({
            "threads": [
                {"id": 1, "name": "Main Thread", "state": "suspended", "isMain": True},
            ]
        }),
        "expression": json.dumps({
            "expression": "player.Health", "status": "submitted",
            "note": "Use Rider's Immediate Window for full evaluation",
        }),
        "isPaused": json.dumps({
            "active": True, "paused": False, "stopped": False, "sessionId": "session-123",
        }),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        # Check custom overrides first
        if path in custom:
            return custom[path]

        # /api/about
        if path == "/api/about":
            return httpx.Response(200, json={"name": "Rider", "version": "2024.1"})

        # /api/file (open file at line)
        if path == "/api/file":
            return httpx.Response(200, text="OK")

        # /api/internal/executeAction/*
        if path.startswith("/api/internal/executeAction/"):
            action = path.split("/")[-1]
            return httpx.Response(200, json={"success": True, "action": action})

        # /api/internal/runScript
        if path == "/api/internal/runScript":
            body = request.content.decode("utf-8") if request.content else ""
            # Match script to response by checking for keywords
            for keyword, resp_json in _script_responses.items():
                if keyword in body:
                    return httpx.Response(200, text=resp_json)
            # Default script response
            return httpx.Response(200, text=json.dumps({"success": True}))

        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def client_with_mocks() -> RiderClient:
    """Create a RiderClient with a pre-configured mock transport."""
    transport = _mock_transport()
    rc = RiderClient(port=63342)
    rc._client = httpx.AsyncClient(transport=transport, base_url="http://localhost:63342")
    rc._base_url = "http://localhost:63342"
    return rc


class TestRiderClientConnection:
    @pytest.mark.asyncio
    async def test_not_connected_raises(self):
        rc = RiderClient(port=99999)
        # list_breakpoints falls back to local cache when not connected,
        # but _run_script will raise RiderConnectionError
        with pytest.raises(RiderConnectionError, match="Not connected"):
            await rc._run_script("test")

    @pytest.mark.asyncio
    async def test_health_check(self, client_with_mocks: RiderClient):
        health = await client_with_mocks.health_check()
        assert health["connected"] is True
        assert health["port"] == 63342

    @pytest.mark.asyncio
    async def test_health_check_includes_session(self, client_with_mocks: RiderClient):
        health = await client_with_mocks.health_check()
        assert "session" in health


class TestBreakpointMethods:
    @pytest.mark.asyncio
    async def test_list_breakpoints(self, client_with_mocks: RiderClient):
        bps = await client_with_mocks.list_breakpoints()
        assert len(bps) == 1
        assert bps[0].id == "bp-Player.cs:42"
        assert bps[0].file == "Player.cs"
        assert bps[0].line == 42

    @pytest.mark.asyncio
    async def test_add_breakpoint(self, client_with_mocks: RiderClient):
        bp = await client_with_mocks.add_breakpoint("Player.cs", 42)
        assert bp.file == "Player.cs"
        assert bp.line == 42
        assert bp.id == "bp-Player.cs:42"
        # Should be in local cache
        assert bp.id in client_with_mocks._breakpoints

    @pytest.mark.asyncio
    async def test_remove_breakpoint(self, client_with_mocks: RiderClient):
        await client_with_mocks.add_breakpoint("Player.cs", 42)
        result = await client_with_mocks.remove_breakpoint("bp-Player.cs:42")
        assert result is True
        assert "bp-Player.cs:42" not in client_with_mocks._breakpoints

    @pytest.mark.asyncio
    async def test_enable_disable_breakpoint(self, client_with_mocks: RiderClient):
        await client_with_mocks.add_breakpoint("Player.cs", 42)
        await client_with_mocks.disable_breakpoint("bp-Player.cs:42")
        assert client_with_mocks._breakpoints["bp-Player.cs:42"].enabled is False
        await client_with_mocks.enable_breakpoint("bp-Player.cs:42")
        assert client_with_mocks._breakpoints["bp-Player.cs:42"].enabled is True


class TestDebugControl:
    @pytest.mark.asyncio
    async def test_start_debug(self, client_with_mocks: RiderClient):
        session = await client_with_mocks.start_debug("MyApp")
        assert session.session_id.startswith("session-")
        assert session.status == DebugSessionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_stop_debug(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.stop_debug()
        assert result is True

    @pytest.mark.asyncio
    async def test_pause(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.pause()
        assert result is True

    @pytest.mark.asyncio
    async def test_resume(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.resume()
        assert result is True

    @pytest.mark.asyncio
    async def test_step_over(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.step_over()
        assert result["success"] is True
        assert result["action"] == "StepOver"

    @pytest.mark.asyncio
    async def test_step_into(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.step_into()
        assert result["success"] is True
        assert result["action"] == "StepInto"

    @pytest.mark.asyncio
    async def test_step_out(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.step_out()
        assert result["success"] is True
        assert result["action"] == "StepOut"


class TestInspection:
    @pytest.mark.asyncio
    async def test_get_variables(self, client_with_mocks: RiderClient):
        variables = await client_with_mocks.get_variables()
        assert len(variables) == 1
        assert variables[0].name == "health"
        assert variables[0].value == "100"

    @pytest.mark.asyncio
    async def test_evaluate_expression(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.evaluate_expression("player.Health")
        assert result["expression"] == "player.Health"
        assert result["status"] == "submitted"

    @pytest.mark.asyncio
    async def test_get_stack_trace(self, client_with_mocks: RiderClient):
        frames = await client_with_mocks.get_stack_trace()
        assert len(frames) == 1
        assert frames[0].method_name == "Player.TakeDamage"
        assert frames[0].file == "Player.cs"
        assert frames[0].line == 42

    @pytest.mark.asyncio
    async def test_get_threads(self, client_with_mocks: RiderClient):
        threads = await client_with_mocks.get_threads()
        assert len(threads) == 1
        assert threads[0].thread_id == 1
        assert threads[0].is_main is True
