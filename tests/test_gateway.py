"""Unit tests for RiderClient (mocked HTTP responses)."""

import httpx
import pytest

from rider_debug_mcp.gateway.client import _API, RiderClient, RiderConnectionError
from rider_debug_mcp.gateway.models import DebugSessionStatus


def _mock_transport() -> httpx.MockTransport:
    """Create a mock transport that simulates the Rider plugin API."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        # Built-in endpoints
        if path == "/api/about":
            return httpx.Response(200, json={"name": "Rider", "version": "2025.1"})

        # Plugin API — strip prefix
        if not path.startswith(_API):
            return httpx.Response(404)
        ep = path[len(_API):]

        # Status
        if ep == "/status":
            return httpx.Response(200, json={
                "plugin": "rider-debug-mcp", "version": "0.1.0",
                "active": True, "paused": False, "stopped": False, "project": "TestProject",
            })

        # Breakpoints
        if ep == "/breakpoints" and request.method == "GET":
            return httpx.Response(200, json={
                "breakpoints": [
                    {"id": "bp-Player.cs:42", "file": "Player.cs", "line": 42, "enabled": True},
                ]
            })
        if ep == "/breakpoints" and request.method == "POST":
            return httpx.Response(200, json={
                "id": "bp-Player.cs:42", "file": "Player.cs", "line": 42, "enabled": True,
            })
        if ep.startswith("/breakpoints/") and request.method == "DELETE":
            return httpx.Response(200, json={"removed": True, "id": ep.split("/")[-1]})
        if ep.endswith("/enable") and request.method == "POST":
            return httpx.Response(200, json={"enabled": True})
        if ep.endswith("/disable") and request.method == "POST":
            return httpx.Response(200, json={"enabled": False})

        # Debug control
        if ep == "/debug/start" and request.method == "POST":
            return httpx.Response(200, json={
                "sessionId": "session-123", "status": "starting", "configuration": "MyApp",
            })
        if ep in ("/debug/stop", "/debug/pause", "/debug/resume"):
            return httpx.Response(200, json={"success": True})
        if ep in ("/debug/stepOver", "/debug/stepInto", "/debug/stepOut"):
            action = ep.split("/")[-1]
            return httpx.Response(200, json={"success": True, "action": action})

        # Inspection
        if ep == "/debug/variables":
            return httpx.Response(200, json={
                "variables": [
                    {"name": "health", "value": "100", "type": "System.Int32", "hasChildren": False},
                ],
            })
        if ep == "/debug/evaluate":
            return httpx.Response(200, json={
                "expression": "player.Health", "result": "100", "type": "System.Int32",
            })
        if ep == "/debug/stackTrace":
            return httpx.Response(200, json={
                "frames": [
                    {"method": "Player.TakeDamage", "file": "Player.cs", "line": 42, "module": "Assembly-CSharp"},
                ],
            })
        if ep == "/debug/threads":
            return httpx.Response(200, json={
                "threads": [
                    {"id": 1, "name": "Main Thread", "state": "suspended", "isMain": True},
                ],
            })

        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def client_with_mocks() -> RiderClient:
    """Create a RiderClient with a pre-configured mock transport."""
    transport = _mock_transport()
    rc = RiderClient(port=63342)
    rc._client = httpx.AsyncClient(transport=transport, base_url="http://localhost:63342")
    rc._base_url = "http://localhost:63342"
    rc._plugin_available = True
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
        assert health["plugin_installed"] is True

    @pytest.mark.asyncio
    async def test_plugin_detection(self, client_with_mocks: RiderClient):
        await client_with_mocks._check_plugin()
        assert client_with_mocks._plugin_available is True


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

    @pytest.mark.asyncio
    async def test_remove_breakpoint(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.remove_breakpoint("bp-Player.cs:42")
        assert result is True

    @pytest.mark.asyncio
    async def test_enable_breakpoint(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.enable_breakpoint("bp-Player.cs:42")
        assert result is True

    @pytest.mark.asyncio
    async def test_disable_breakpoint(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.disable_breakpoint("bp-Player.cs:42")
        assert result is True


class TestDebugControl:
    @pytest.mark.asyncio
    async def test_start_debug(self, client_with_mocks: RiderClient):
        session = await client_with_mocks.start_debug("MyApp")
        assert session.session_id == "session-123"
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

    @pytest.mark.asyncio
    async def test_step_into(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.step_into()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_step_out(self, client_with_mocks: RiderClient):
        result = await client_with_mocks.step_out()
        assert result["success"] is True


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
