"""Unit tests for RiderClient (mocked HTTP responses)."""

import httpx
import pytest

from rider_debug_mcp.gateway.client import RiderClient, RiderConnectionError
from rider_debug_mcp.gateway.models import DebugSessionStatus


def _mock_transport(responses: dict[str, httpx.Response]) -> httpx.MockTransport:
    """Create a mock transport that returns canned responses by path."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in responses:
            return responses[path]
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def client_with_mocks() -> RiderClient:
    """Create a RiderClient with a pre-configured mock transport."""
    responses = {
        "/api/about": httpx.Response(200, json={"name": "Rider", "version": "2024.1"}),
        "/api/debug/breakpoints": httpx.Response(
            200,
            json={
                "breakpoints": [
                    {"id": "bp-1", "file": "Player.cs", "line": 42, "enabled": True},
                ]
            },
        ),
        "/api/debug/start": httpx.Response(200, json={"sessionId": "s-1"}),
        "/api/debug/stop": httpx.Response(200, json={"status": "stopped"}),
        "/api/debug/pause": httpx.Response(200, json={"status": "paused"}),
        "/api/debug/resume": httpx.Response(200, json={"status": "running"}),
        "/api/debug/stepOver": httpx.Response(200, json={"file": "Player.cs", "line": 43}),
        "/api/debug/stepInto": httpx.Response(200, json={"file": "Player.cs", "line": 10}),
        "/api/debug/stepOut": httpx.Response(200, json={"file": "Player.cs", "line": 50}),
        "/api/debug/variables": httpx.Response(
            200,
            json={
                "variables": [
                    {"name": "health", "value": "100", "type": "System.Int32", "hasChildren": False},
                ]
            },
        ),
        "/api/debug/evaluate": httpx.Response(200, json={"result": "100", "type": "System.Int32"}),
        "/api/debug/stackTrace": httpx.Response(
            200,
            json={
                "frames": [
                    {"method": "Player.TakeDamage", "file": "Player.cs", "line": 42, "module": "Assembly-CSharp"},
                ]
            },
        ),
        "/api/debug/threads": httpx.Response(
            200,
            json={
                "threads": [
                    {"id": 1, "name": "Main Thread", "state": "suspended", "isMain": True},
                ]
            },
        ),
    }

    transport = _mock_transport(responses)
    rc = RiderClient(port=63342)
    rc._client = httpx.AsyncClient(transport=transport, base_url="http://localhost:63342")
    rc._base_url = "http://localhost:63342"
    return rc


class TestRiderClientConnection:
    @pytest.mark.asyncio
    async def test_not_connected_raises(self):
        rc = RiderClient(port=99999)
        with pytest.raises(RiderConnectionError, match="Not connected"):
            await rc.list_breakpoints()

    @pytest.mark.asyncio
    async def test_health_check(self, client_with_mocks: RiderClient):
        health = await client_with_mocks.health_check()
        assert health["connected"] is True
        assert health["port"] == 63342


class TestBreakpointMethods:
    @pytest.mark.asyncio
    async def test_list_breakpoints(self, client_with_mocks: RiderClient):
        bps = await client_with_mocks.list_breakpoints()
        assert len(bps) == 1
        assert bps[0].id == "bp-1"
        assert bps[0].file == "Player.cs"
        assert bps[0].line == 42

    @pytest.mark.asyncio
    async def test_add_breakpoint(self, client_with_mocks: RiderClient):
        # Mock POST to /api/debug/breakpoints returns the list response but we're POSTing
        # For a simple test, we just verify it doesn't crash and returns a Breakpoint
        # Override the mock response for POST by using the existing one
        bp = await client_with_mocks.add_breakpoint("Player.cs", 42)
        assert bp.file == "Player.cs"
        assert bp.line == 42


class TestDebugControl:
    @pytest.mark.asyncio
    async def test_start_debug(self, client_with_mocks: RiderClient):
        session = await client_with_mocks.start_debug("MyApp")
        assert session.session_id == "s-1"
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
        assert result["line"] == 43

    @pytest.mark.asyncio
    async def test_step_into(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.step_into()
        assert result["line"] == 10

    @pytest.mark.asyncio
    async def test_step_out(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.step_out()
        assert result["line"] == 50


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
        assert result["result"] == "100"

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
