"""Rider IDE HTTP client for debug operations."""

from __future__ import annotations

import logging
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


class RiderConnectionError(Exception):
    """Raised when the client cannot connect to Rider IDE."""


class RiderClient:
    """Async HTTP client for JetBrains Rider built-in server.

    Handles port auto-discovery and provides methods for breakpoint management,
    debug control, and runtime inspection.
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

    # --- Connection management ---

    async def connect(self) -> None:
        """Connect to Rider IDE. Auto-discovers port if not specified.

        Raises:
            RiderConnectionError: If Rider is not reachable.
        """
        if self._port is not None:
            self._base_url = f"http://{self._host}:{self._port}"
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
            if not await self._check_connection():
                await self._client.aclose()
                self._client = None
                raise RiderConnectionError(
                    f"Cannot connect to Rider at {self._base_url}. "
                    "Ensure Rider is running and the built-in server is enabled."
                )
            return

        # Auto-discover port
        for port in range(DEFAULT_PORT_RANGE_START, DEFAULT_PORT_RANGE_END + 1):
            base_url = f"http://{self._host}:{port}"
            client = httpx.AsyncClient(base_url=base_url, timeout=self._timeout)
            try:
                resp = await client.get("/api/about")
                if resp.status_code == 200:
                    self._port = port
                    self._base_url = base_url
                    self._client = client
                    logger.info("Discovered Rider on port %d", port)
                    return
            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            finally:
                if self._client is None or self._client is not client:
                    await client.aclose()

        raise RiderConnectionError(
            f"No Rider instance found on ports {DEFAULT_PORT_RANGE_START}-{DEFAULT_PORT_RANGE_END}. "
            "Ensure Rider is running and the built-in server is enabled."
        )

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _check_connection(self) -> bool:
        """Test whether the current base URL responds."""
        try:
            resp = await self._client.get("/api/about")  # type: ignore[union-attr]
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def health_check(self) -> dict[str, Any]:
        """Return connection health information."""
        connected = self._client is not None and await self._check_connection()
        return {
            "connected": connected,
            "host": self._host,
            "port": self._port,
            "base_url": self._base_url,
        }

    # --- Internal helpers ---

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an HTTP request and return the JSON response.

        Raises:
            RiderConnectionError: On connection / timeout / non-200 errors.
        """
        if self._client is None:
            raise RiderConnectionError("Not connected. Call connect() first.")

        try:
            resp = await self._client.request(method, path, json=json, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RiderConnectionError(f"Connection refused: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RiderConnectionError(f"Request timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise RiderConnectionError(f"HTTP error {exc.response.status_code}: {exc.response.text}") from exc

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        return await self._request("GET", path, params=params or None)

    async def _post(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("POST", path, json=data)

    async def _delete(self, path: str) -> dict[str, Any]:
        return await self._request("DELETE", path)

    # --- Breakpoint management (task 6.2) ---

    async def add_breakpoint(
        self,
        file: str,
        line: int,
        condition: str | None = None,
    ) -> Breakpoint:
        """Add a breakpoint at the specified file and line."""
        payload: dict[str, Any] = {"file": file, "line": line}
        if condition:
            payload["condition"] = condition

        data = await self._post("/api/debug/breakpoints", payload)
        return Breakpoint(
            id=data.get("id", f"bp-{file}:{line}"),
            file=file,
            line=line,
            enabled=data.get("enabled", True),
            condition=condition,
            breakpoint_type=BreakpointType.CONDITIONAL if condition else BreakpointType.LINE,
        )

    async def remove_breakpoint(self, breakpoint_id: str) -> bool:
        """Remove a breakpoint by ID."""
        await self._delete(f"/api/debug/breakpoints/{breakpoint_id}")
        return True

    async def enable_breakpoint(self, breakpoint_id: str) -> bool:
        """Enable a breakpoint."""
        await self._post(f"/api/debug/breakpoints/{breakpoint_id}/enable")
        return True

    async def disable_breakpoint(self, breakpoint_id: str) -> bool:
        """Disable a breakpoint."""
        await self._post(f"/api/debug/breakpoints/{breakpoint_id}/disable")
        return True

    async def list_breakpoints(self) -> list[Breakpoint]:
        """List all breakpoints."""
        data = await self._get("/api/debug/breakpoints")
        breakpoints_data = data.get("breakpoints", [])
        return [
            Breakpoint(
                id=bp["id"],
                file=bp.get("file", ""),
                line=bp.get("line", 1),
                enabled=bp.get("enabled", True),
                condition=bp.get("condition"),
            )
            for bp in breakpoints_data
        ]

    # --- Debug control (task 6.3) ---

    async def start_debug(self, configuration_name: str | None = None) -> DebugSession:
        """Start a debug session."""
        payload: dict[str, Any] = {}
        if configuration_name:
            payload["configuration"] = configuration_name

        data = await self._post("/api/debug/start", payload)
        return DebugSession(
            session_id=data.get("sessionId", "unknown"),
            status=DebugSessionStatus.RUNNING,
            configuration_name=configuration_name,
        )

    async def stop_debug(self) -> bool:
        """Stop the current debug session."""
        await self._post("/api/debug/stop")
        return True

    async def pause(self) -> bool:
        """Pause the current debug session."""
        await self._post("/api/debug/pause")
        return True

    async def resume(self) -> bool:
        """Resume execution."""
        await self._post("/api/debug/resume")
        return True

    async def step_over(self) -> dict[str, Any]:
        """Step over the current line."""
        return await self._post("/api/debug/stepOver")

    async def step_into(self) -> dict[str, Any]:
        """Step into the current function call."""
        return await self._post("/api/debug/stepInto")

    async def step_out(self) -> dict[str, Any]:
        """Step out of the current function."""
        return await self._post("/api/debug/stepOut")

    # --- Inspection (task 6.4) ---

    async def get_variables(self, frame_index: int = 0) -> list[Variable]:
        """Get local variables for the given stack frame."""
        data = await self._get("/api/debug/variables", frameIndex=frame_index)
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
        """Evaluate an expression in the current debug context."""
        return await self._post("/api/debug/evaluate", {"expression": expression})

    async def get_stack_trace(self, thread_id: int | None = None) -> list[StackFrame]:
        """Get the stack trace for the given thread."""
        params: dict[str, Any] = {}
        if thread_id is not None:
            params["threadId"] = thread_id

        data = await self._get("/api/debug/stackTrace", **params)
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
        """Get the list of threads in the debug session."""
        data = await self._get("/api/debug/threads")
        return [
            ThreadInfo(
                thread_id=t["id"],
                name=t.get("name"),
                state=t.get("state", "running"),
                is_main=t.get("isMain", False),
            )
            for t in data.get("threads", [])
        ]
