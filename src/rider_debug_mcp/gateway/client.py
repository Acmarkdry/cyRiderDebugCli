"""Rider IDE HTTP client for debug operations.

Communicates with JetBrains Rider via the built-in HTTP server.
Requires the companion Rider plugin (rider-plugin/) to expose debug endpoints:

  GET  /api/about                           → IDE identity (built-in)
  *    /api/rider-debug-mcp/*               → debug operations (plugin)

Install the plugin: python install_plugin.py
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from rider_debug_mcp.gateway.models import (
    Breakpoint,
    BreakpointType,
    DebugSession,
    DebugSessionStatus,
    StackFrame,
    ThreadInfo,
    Variable,
)

logger = logging.getLogger(__name__)

DEFAULT_PORT_RANGE_START = 63342
DEFAULT_PORT_RANGE_END = 63352
DEFAULT_TIMEOUT = 5.0

# Plugin API prefix
_API = "/api/rider-debug-mcp"


class RiderConnectionError(Exception):
    """Raised when the client cannot connect to Rider IDE."""


class RiderClient:
    """Async HTTP client for JetBrains Rider debug operations.

    Requires the companion Rider plugin to expose REST endpoints under
    /api/rider-debug-mcp/*. The plugin bridges HTTP calls to Rider's
    internal XDebuggerManager, RunManager, and XBreakpointManager APIs.

    Install: python install_plugin.py
    """

    def __init__(
        self,
        port: int | None = None,
        host: str = "localhost",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._base_url: str | None = None
        self._plugin_available: bool = False

    @property
    def port(self) -> int | None:
        return self._port

    # --- Connection management ---

    async def connect(self) -> None:
        """Connect to Rider IDE. Auto-discovers port if not specified."""
        if self._port is not None:
            self._base_url = f"http://{self._host}:{self._port}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout,
                headers={"Origin": f"http://{self._host}:{self._port}"},
            )
            if not await self._check_connection():
                await self._client.aclose()
                self._client = None
                raise RiderConnectionError(
                    f"Cannot connect to Rider at {self._base_url}. "
                    "Ensure Rider is running."
                )
            await self._check_plugin()
            return

        for port in range(DEFAULT_PORT_RANGE_START, DEFAULT_PORT_RANGE_END + 1):
            base_url = f"http://{self._host}:{port}"
            client = httpx.AsyncClient(
                base_url=base_url, timeout=self._timeout,
                headers={"Origin": base_url},
            )
            try:
                resp = await client.get("/api/about")
                if resp.status_code == 200:
                    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    product = data.get("name", "") if isinstance(data, dict) else ""
                    logger.info("Found JetBrains IDE on port %d (%s)", port, product)
                    self._port = port
                    self._base_url = base_url
                    self._client = client
                    await self._check_plugin()
                    return
            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            except Exception:
                pass
            finally:
                if self._client is None or self._client is not client:
                    await client.aclose()

        raise RiderConnectionError(
            f"No Rider instance found on ports {DEFAULT_PORT_RANGE_START}-{DEFAULT_PORT_RANGE_END}."
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _check_connection(self) -> bool:
        try:
            resp = await self._client.get("/api/about")  # type: ignore[union-attr]
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def _check_plugin(self) -> None:
        """Check if the companion plugin is installed."""
        try:
            resp = await self._client.get(f"{_API}/status")  # type: ignore[union-attr]
            self._plugin_available = resp.status_code == 200
            if self._plugin_available:
                logger.info("Rider Debug MCP plugin detected ✓")
            else:
                logger.warning(
                    "Rider Debug MCP plugin NOT detected (HTTP %d). "
                    "Install it: python install_plugin.py",
                    resp.status_code,
                )
        except Exception:
            self._plugin_available = False
            logger.warning("Rider Debug MCP plugin NOT detected. Install it: python install_plugin.py")

    async def health_check(self) -> dict[str, Any]:
        connected = self._client is not None and await self._check_connection()
        result: dict[str, Any] = {
            "connected": connected,
            "host": self._host,
            "port": self._port,
            "base_url": self._base_url,
            "plugin_installed": self._plugin_available,
        }
        if connected and self._plugin_available:
            try:
                resp = await self._client.get(f"{_API}/status")  # type: ignore[union-attr]
                if resp.status_code == 200:
                    result["session"] = resp.json()
            except Exception:
                pass
        return result

    # --- Internal helpers ---

    def _ensure_connected(self) -> None:
        if self._client is None:
            raise RiderConnectionError("Not connected. Call connect() first.")

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        """GET request to plugin API."""
        self._ensure_connected()
        try:
            resp = await self._client.get(f"{_API}{path}", params=params or None)  # type: ignore[union-attr]
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}", "body": resp.text[:300]}
        except httpx.ConnectError as exc:
            raise RiderConnectionError(f"Connection refused: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RiderConnectionError(f"Request timed out: {exc}") from exc

    async def _post(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST request to plugin API."""
        self._ensure_connected()
        try:
            resp = await self._client.post(f"{_API}{path}", json=data or {})  # type: ignore[union-attr]
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    return {"success": True}
            return {"error": f"HTTP {resp.status_code}", "body": resp.text[:300]}
        except httpx.ConnectError as exc:
            raise RiderConnectionError(f"Connection refused: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RiderConnectionError(f"Request timed out: {exc}") from exc

    async def _delete(self, path: str) -> dict[str, Any]:
        """DELETE request to plugin API."""
        self._ensure_connected()
        try:
            resp = await self._client.delete(f"{_API}{path}")  # type: ignore[union-attr]
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}"}
        except httpx.ConnectError as exc:
            raise RiderConnectionError(f"Connection refused: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RiderConnectionError(f"Request timed out: {exc}") from exc

    # --- Breakpoint management ---

    async def add_breakpoint(
        self,
        file: str,
        line: int,
        condition: str | None = None,
    ) -> Breakpoint:
        data: dict[str, Any] = {"file": file, "line": line}
        if condition:
            data["condition"] = condition
        result = await self._post("/breakpoints", data)
        return Breakpoint(
            id=result.get("id", f"bp-{file}:{line}"),
            file=file,
            line=line,
            enabled=result.get("enabled", True),
            condition=condition,
            breakpoint_type=BreakpointType.CONDITIONAL if condition else BreakpointType.LINE,
        )

    async def remove_breakpoint(self, breakpoint_id: str) -> bool:
        result = await self._delete(f"/breakpoints/{breakpoint_id}")
        return result.get("removed", False) or "error" not in result

    async def enable_breakpoint(self, breakpoint_id: str) -> bool:
        result = await self._post(f"/breakpoints/{breakpoint_id}/enable")
        return "error" not in result

    async def disable_breakpoint(self, breakpoint_id: str) -> bool:
        result = await self._post(f"/breakpoints/{breakpoint_id}/disable")
        return "error" not in result

    async def list_breakpoints(self) -> list[Breakpoint]:
        data = await self._get("/breakpoints")
        return [
            Breakpoint(
                id=bp.get("id", "unknown"),
                file=bp.get("file", ""),
                line=bp.get("line", 1),
                enabled=bp.get("enabled", True),
                condition=bp.get("condition"),
            )
            for bp in data.get("breakpoints", [])
        ]

    # --- Debug control ---

    async def start_debug(self, configuration_name: str | None = None) -> DebugSession:
        data: dict[str, Any] = {}
        if configuration_name:
            data["configuration"] = configuration_name
        result = await self._post("/debug/start", data)
        return DebugSession(
            session_id=result.get("sessionId", f"session-{int(time.time())}"),
            status=DebugSessionStatus.RUNNING,
            configuration_name=configuration_name,
        )

    async def stop_debug(self) -> bool:
        await self._post("/debug/stop")
        return True

    async def pause(self) -> bool:
        await self._post("/debug/pause")
        return True

    async def resume(self) -> bool:
        await self._post("/debug/resume")
        return True

    async def step_over(self) -> dict[str, Any]:
        return await self._post("/debug/stepOver")

    async def step_into(self) -> dict[str, Any]:
        return await self._post("/debug/stepInto")

    async def step_out(self) -> dict[str, Any]:
        return await self._post("/debug/stepOut")

    # --- Inspection ---

    async def get_variables(self, frame_index: int = 0) -> list[Variable]:
        data = await self._get("/debug/variables", frameIndex=frame_index)
        return [
            Variable(
                name=v["name"],
                value=v.get("value", ""),
                type_name=v.get("type", "unknown"),
                has_children=v.get("hasChildren", False),
            )
            for v in data.get("variables", [])
        ]

    async def evaluate_expression(self, expression: str) -> dict[str, Any]:
        return await self._post("/debug/evaluate", {"expression": expression})

    async def get_stack_trace(self, thread_id: int | None = None) -> list[StackFrame]:
        params: dict[str, Any] = {}
        if thread_id is not None:
            params["threadId"] = thread_id
        data = await self._get("/debug/stackTrace", **params)
        return [
            StackFrame(
                index=i,
                method_name=f.get("method", "unknown"),
                file=f.get("file"),
                line=f.get("line"),
                module=f.get("module"),
            )
            for i, f in enumerate(data.get("frames", []))
        ]

    async def get_threads(self) -> list[ThreadInfo]:
        data = await self._get("/debug/threads")
        return [
            ThreadInfo(
                thread_id=t["id"],
                name=t.get("name"),
                state=t.get("state", "running"),
                is_main=t.get("isMain", False),
            )
            for t in data.get("threads", [])
        ]
