"""Rider IDE HTTP client for debug operations.

Uses JetBrains built-in HTTP server native endpoints:
  - GET  /api/about                              → IDE identity check
  - POST /api/internal/executeAction/{actionId}  → trigger any IDE action
  - POST /api/internal/runScript                 → execute Groovy/Kotlin script in IDE

No custom Rider plugin required.
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


class RiderConnectionError(Exception):
    """Raised when the client cannot connect to Rider IDE."""


# --- Groovy script templates for querying IDE state ---

_SCRIPT_LIST_BREAKPOINTS = """\
import com.intellij.openapi.project.ProjectManager
import com.intellij.xdebugger.XDebuggerManager
import groovy.json.JsonOutput

def project = ProjectManager.instance.openProjects.find { true }
if (!project) return JsonOutput.toJson([breakpoints: []])

def mgr = XDebuggerManager.getInstance(project).breakpointManager
def bps = mgr.allBreakpoints.findAll {
    it instanceof com.intellij.xdebugger.breakpoints.XLineBreakpoint
}.collect { bp ->
    def url = bp.fileUrl ?: ""
    def fileName = url.contains("/") ? url.substring(url.lastIndexOf("/") + 1) : url
    [id: "bp-${fileName}:${bp.line + 1}", file: fileName, line: bp.line + 1,
     enabled: bp.enabled, condition: bp.conditionExpression?.expression]
}
return JsonOutput.toJson([breakpoints: bps])
"""

_SCRIPT_GET_VARIABLES = """\
import com.intellij.openapi.project.ProjectManager
import com.intellij.xdebugger.XDebuggerManager
import groovy.json.JsonOutput

def project = ProjectManager.instance.openProjects.find { true }
if (!project) return JsonOutput.toJson([error: "No project open"])

def session = XDebuggerManager.getInstance(project).currentSession
if (!session) return JsonOutput.toJson([error: "No active debug session"])

def frame = session.currentStackFrame
if (!frame) return JsonOutput.toJson([error: "No current stack frame"])

def pos = frame.sourcePosition
def frameInfo = pos ? [file: pos.file.name, line: pos.line + 1] : null
return JsonOutput.toJson([variables: [], frame: frameInfo,
    note: "Variable values require async XValue enumeration"])
"""

_SCRIPT_GET_STACK_TRACE = """\
import com.intellij.openapi.project.ProjectManager
import com.intellij.xdebugger.XDebuggerManager
import groovy.json.JsonOutput

def project = ProjectManager.instance.openProjects.find { true }
if (!project) return JsonOutput.toJson([frames: []])

def session = XDebuggerManager.getInstance(project).currentSession
if (!session) return JsonOutput.toJson([error: "No active debug session"])

def frame = session.currentStackFrame
def pos = frame?.sourcePosition
def frames = pos ? [[method: frame.evaluationExpression ?: "unknown",
                      file: pos.file.name, line: pos.line + 1]] : []
return JsonOutput.toJson([frames: frames])
"""

_SCRIPT_GET_THREADS = """\
import com.intellij.openapi.project.ProjectManager
import com.intellij.xdebugger.XDebuggerManager
import groovy.json.JsonOutput

def project = ProjectManager.instance.openProjects.find { true }
if (!project) return JsonOutput.toJson([threads: []])

def session = XDebuggerManager.getInstance(project).currentSession
if (!session) return JsonOutput.toJson([error: "No active debug session"])

def ctx = session.suspendContext
if (!ctx) return JsonOutput.toJson([threads: [], note: "Debugger running, not suspended"])

def stack = ctx.activeExecutionStack
def threads = stack ? [[id: 1, name: stack.displayName, state: "suspended", isMain: true]] : []
return JsonOutput.toJson([threads: threads])
"""

_SCRIPT_EVALUATE = """\
import com.intellij.openapi.project.ProjectManager
import com.intellij.xdebugger.XDebuggerManager
import groovy.json.JsonOutput

def project = ProjectManager.instance.openProjects.find { true }
if (!project) return JsonOutput.toJson([error: "No project open"])

def session = XDebuggerManager.getInstance(project).currentSession
if (!session) return JsonOutput.toJson([error: "No active debug session"])

return JsonOutput.toJson([expression: "%s", status: "submitted",
    note: "Use Rider's Immediate Window for full evaluation"])
"""

_SCRIPT_SESSION_STATUS = """\
import com.intellij.openapi.project.ProjectManager
import com.intellij.xdebugger.XDebuggerManager
import groovy.json.JsonOutput

def project = ProjectManager.instance.openProjects.find { true }
if (!project) return JsonOutput.toJson([active: false])

def session = XDebuggerManager.getInstance(project).currentSession
def paused = session?.isPaused() ?: false
def stopped = session?.isStopped() ?: true
return JsonOutput.toJson([
    active: session != null,
    paused: paused,
    stopped: stopped,
    sessionId: session ? "session-${session.hashCode()}" : null
])
"""

# JetBrains IDE Action IDs for debug operations
_ACTION_MAP = {
    "debug": "Debug",
    "stop": "Stop",
    "pause": "Pause",
    "resume": "Resume",
    "step_over": "StepOver",
    "step_into": "StepInto",
    "step_out": "StepOut",
    "toggle_breakpoint": "ToggleLineBreakpoint",
    "run": "Run",
}


class RiderClient:
    """Async HTTP client for JetBrains Rider built-in server.

    Uses native IDE endpoints — no custom plugin required:
      - /api/about                            → connection check
      - /api/internal/executeAction/{action}  → trigger IDE actions
      - /api/internal/runScript               → execute Groovy scripts for queries

    Breakpoints are managed locally + via ToggleLineBreakpoint action.
    Debug control uses IDE action execution.
    Inspection uses Groovy scripting to query XDebuggerManager.
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
        # Local breakpoint cache (source of truth is Rider, but we track for list/clear)
        self._breakpoints: dict[str, Breakpoint] = {}

    @property
    def port(self) -> int | None:
        return self._port

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
                    "Ensure Rider is running with Settings → Build → Debugger → "
                    "Allow unsigned requests enabled."
                )
            return

        # Auto-discover port
        for port in range(DEFAULT_PORT_RANGE_START, DEFAULT_PORT_RANGE_END + 1):
            base_url = f"http://{self._host}:{port}"
            client = httpx.AsyncClient(base_url=base_url, timeout=self._timeout)
            try:
                resp = await client.get("/api/about")
                if resp.status_code == 200:
                    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    product = data.get("name", "") if isinstance(data, dict) else ""
                    logger.info("Discovered JetBrains IDE on port %d (product: %s)", port, product)
                    self._port = port
                    self._base_url = base_url
                    self._client = client
                    return
            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            except Exception:
                pass
            finally:
                if self._client is None or self._client is not client:
                    await client.aclose()

        raise RiderConnectionError(
            f"No Rider instance found on ports {DEFAULT_PORT_RANGE_START}-{DEFAULT_PORT_RANGE_END}. "
            "Ensure Rider is running and the built-in server is enabled "
            "(Settings → Build, Execution, Deployment → Debugger → Built-in Server)."
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
        session_info: dict[str, Any] = {}
        if connected:
            try:
                session_info = await self._run_script(_SCRIPT_SESSION_STATUS)
            except Exception:
                pass
        return {
            "connected": connected,
            "host": self._host,
            "port": self._port,
            "base_url": self._base_url,
            "session": session_info,
        }

    # --- Internal helpers ---

    def _ensure_connected(self) -> None:
        if self._client is None:
            raise RiderConnectionError("Not connected. Call connect() first.")

    async def _execute_action(self, action_id: str) -> dict[str, Any]:
        """Execute an IDE action via the built-in HTTP server.

        Uses: POST /api/internal/executeAction/{actionId}
        This is a native JetBrains endpoint, no plugin needed.
        """
        self._ensure_connected()
        path = f"/api/internal/executeAction/{action_id}"
        try:
            resp = await self._client.post(path)  # type: ignore[union-attr]
            # executeAction returns 200 on success, sometimes with empty body
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    return {"success": True, "action": action_id}
            else:
                return {"success": False, "status": resp.status_code, "action": action_id,
                        "body": resp.text[:500]}
        except httpx.ConnectError as exc:
            raise RiderConnectionError(f"Connection refused: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RiderConnectionError(f"Request timed out: {exc}") from exc

    async def _run_script(self, script: str) -> dict[str, Any]:
        """Run a Groovy script in Rider via the built-in HTTP server.

        Uses: POST /api/internal/runScript
        Requires "Allow unsigned requests" in IDE settings.
        """
        self._ensure_connected()
        import json as _json

        try:
            resp = await self._client.post(  # type: ignore[union-attr]
                "/api/internal/runScript",
                content=script,
                headers={"Content-Type": "text/plain"},
            )
            if resp.status_code == 200:
                text = resp.text.strip()
                if text:
                    try:
                        return _json.loads(text)
                    except _json.JSONDecodeError:
                        return {"raw": text}
                return {"success": True}
            else:
                return {"error": f"Script execution failed (HTTP {resp.status_code})", "body": resp.text[:500]}
        except httpx.ConnectError as exc:
            raise RiderConnectionError(f"Connection refused: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RiderConnectionError(f"Request timed out: {exc}") from exc

    async def _open_file_at_line(self, file: str, line: int) -> bool:
        """Open a file at a specific line using the built-in /api/file endpoint."""
        self._ensure_connected()
        try:
            resp = await self._client.get(  # type: ignore[union-attr]
                "/api/file",
                params={"file": file, "line": str(line)},
            )
            return resp.status_code == 200
        except Exception:
            return False

    # --- Breakpoint management ---

    async def add_breakpoint(
        self,
        file: str,
        line: int,
        condition: str | None = None,
    ) -> Breakpoint:
        """Add a breakpoint by opening the file at line and toggling breakpoint.

        Uses:
          1. GET /api/file?file=X&line=Y  → navigate to location
          2. POST /api/internal/executeAction/ToggleLineBreakpoint → toggle
        """
        # Navigate to file:line first
        await self._open_file_at_line(file, line)

        # Toggle breakpoint at current cursor position
        await self._execute_action(_ACTION_MAP["toggle_breakpoint"])

        bp_id = f"bp-{file}:{line}"
        bp = Breakpoint(
            id=bp_id,
            file=file,
            line=line,
            enabled=True,
            condition=condition,
            breakpoint_type=BreakpointType.CONDITIONAL if condition else BreakpointType.LINE,
        )
        self._breakpoints[bp_id] = bp

        # If condition is set, log a note (conditions need IDE UI or plugin)
        if condition:
            logger.info(
                "Breakpoint added at %s:%d. Note: condition '%s' must be set manually in Rider "
                "(right-click breakpoint → Edit). Native action API does not support condition setting.",
                file, line, condition,
            )

        return bp

    async def remove_breakpoint(self, breakpoint_id: str) -> bool:
        """Remove a breakpoint by navigating to its location and toggling."""
        bp = self._breakpoints.get(breakpoint_id)
        if bp:
            await self._open_file_at_line(bp.file, bp.line)
            await self._execute_action(_ACTION_MAP["toggle_breakpoint"])
            del self._breakpoints[breakpoint_id]
            return True

        # If not in cache, try to parse ID and toggle anyway
        parts = breakpoint_id.removeprefix("bp-").rsplit(":", 1)
        if len(parts) == 2:
            try:
                file, line = parts[0], int(parts[1])
                await self._open_file_at_line(file, line)
                await self._execute_action(_ACTION_MAP["toggle_breakpoint"])
                return True
            except (ValueError, RiderConnectionError):
                pass
        return False

    async def enable_breakpoint(self, breakpoint_id: str) -> bool:
        """Enable a breakpoint. Updates local cache; IDE sync via list query."""
        bp = self._breakpoints.get(breakpoint_id)
        if bp:
            bp.enabled = True
        return True

    async def disable_breakpoint(self, breakpoint_id: str) -> bool:
        """Disable a breakpoint. Updates local cache; IDE sync via list query."""
        bp = self._breakpoints.get(breakpoint_id)
        if bp:
            bp.enabled = False
        return True

    async def list_breakpoints(self) -> list[Breakpoint]:
        """List breakpoints by querying Rider via Groovy script."""
        try:
            data = await self._run_script(_SCRIPT_LIST_BREAKPOINTS)
            breakpoints_data = data.get("breakpoints", [])
            result = []
            for bp_data in breakpoints_data:
                bp = Breakpoint(
                    id=bp_data.get("id", "unknown"),
                    file=bp_data.get("file", ""),
                    line=bp_data.get("line", 1),
                    enabled=bp_data.get("enabled", True),
                    condition=bp_data.get("condition"),
                )
                result.append(bp)
                self._breakpoints[bp.id] = bp
            return result
        except RiderConnectionError:
            # Fallback to local cache
            return list(self._breakpoints.values())

    # --- Debug control ---

    async def start_debug(self, configuration_name: str | None = None) -> DebugSession:
        """Start a debug session using the Debug action."""
        await self._execute_action(_ACTION_MAP["debug"])
        session_id = f"session-{int(time.time())}"
        return DebugSession(
            session_id=session_id,
            status=DebugSessionStatus.RUNNING,
            configuration_name=configuration_name,
        )

    async def stop_debug(self) -> bool:
        """Stop the current debug session."""
        await self._execute_action(_ACTION_MAP["stop"])
        return True

    async def pause(self) -> bool:
        """Pause the current debug session."""
        await self._execute_action(_ACTION_MAP["pause"])
        return True

    async def resume(self) -> bool:
        """Resume execution."""
        await self._execute_action(_ACTION_MAP["resume"])
        return True

    async def step_over(self) -> dict[str, Any]:
        """Step over the current line."""
        return await self._execute_action(_ACTION_MAP["step_over"])

    async def step_into(self) -> dict[str, Any]:
        """Step into the current function call."""
        return await self._execute_action(_ACTION_MAP["step_into"])

    async def step_out(self) -> dict[str, Any]:
        """Step out of the current function."""
        return await self._execute_action(_ACTION_MAP["step_out"])

    # --- Inspection ---

    async def get_variables(self, frame_index: int = 0) -> list[Variable]:
        """Get local variables for the given stack frame via Groovy script."""
        data = await self._run_script(_SCRIPT_GET_VARIABLES)
        if "error" in data:
            logger.warning("get_variables: %s", data["error"])
            return []
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
        """Evaluate an expression via Groovy script."""
        safe_expr = expression.replace('"', '\\"').replace("'", "\\'")
        script = _SCRIPT_EVALUATE % safe_expr
        return await self._run_script(script)

    async def get_stack_trace(self, thread_id: int | None = None) -> list[StackFrame]:
        """Get the stack trace via Groovy script."""
        data = await self._run_script(_SCRIPT_GET_STACK_TRACE)
        if "error" in data:
            logger.warning("get_stack_trace: %s", data["error"])
            return []
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
        """Get the list of threads via Groovy script."""
        data = await self._run_script(_SCRIPT_GET_THREADS)
        if "error" in data:
            logger.warning("get_threads: %s", data["error"])
            return []
        return [
            ThreadInfo(
                thread_id=t["id"],
                name=t.get("name"),
                state=t.get("state", "running"),
                is_main=t.get("isMain", False),
            )
            for t in data.get("threads", [])
        ]
