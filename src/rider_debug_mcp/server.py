"""MCP Server for Rider Debug – rider_cli and rider_query tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from rider_debug_mcp.analysis.crash import CrashAnalyzer
from rider_debug_mcp.analysis.report import ReportGenerator
from rider_debug_mcp.gateway.client import RiderClient, RiderConnectionError
from rider_debug_mcp.handlers import create_router
from rider_debug_mcp.middleware.models import CommandStatus
from rider_debug_mcp.middleware.parser import CommandParser, ParseError
from rider_debug_mcp.middleware.session import SessionManager

logger = logging.getLogger(__name__)

# --- Tool descriptions ---

RIDER_CLI_DESCRIPTION = """\
Execute Rider debugger commands using CLI syntax.

SYNTAX:
  <command> [positional_args...] [--flag value ...]
  @<target>     Set file context for subsequent commands
  # comment     Ignored
  Multiple lines = batch execution (single round-trip)

BREAKPOINT COMMANDS:
  add_breakpoint <file> <line> [--condition "<expr>"]
  remove_breakpoint <id>
  enable_breakpoint <id>
  disable_breakpoint <id>
  list_breakpoints
  clear_breakpoints

DEBUG CONTROL:
  start_debug [config_name]
  stop_debug
  pause
  resume
  step_over
  step_into
  step_out

INSPECTION:
  get_variables [frame_index]
  evaluate <expression>
  get_stack_trace [thread_id]
  get_threads

ANALYSIS:
  analyze_crash
  crash_report
  crash_history

EXAMPLES:
  # Single command
  add_breakpoint PlayerController.cs 42

  # Batch with context
  @PlayerController.cs
  add_breakpoint 42
  add_breakpoint 55 --condition "health <= 0"
  start_debug
"""

RIDER_QUERY_DESCRIPTION = """\
Query information from Rider debugger.

QUERIES:
  help                    List all available commands
  help <command>          Show command syntax and examples
  context                 Current debug session status
  crash_report            Latest crash analysis report
  crash_history           All crash reports this session
  breakpoints             Current breakpoints list
  health                  Connection health status
"""


def _format_result(data: Any) -> str:
    """Format a result for human-readable CLI text output."""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return _format_list(data)
    if isinstance(data, dict):
        return _format_dict(data)
    return str(data)


def _format_list(items: list[Any]) -> str:
    """Format a list of items as CLI-readable text."""
    if not items:
        return "(empty)"
    # Detect list type by first item
    first = items[0]
    if isinstance(first, dict):
        # Check for known shapes
        if "method_name" in first or "method" in first:
            return _format_stack_frames(items)
        if "name" in first and "value" in first:
            return _format_variables(items)
        if "thread_id" in first or "id" in first and "state" in first:
            return _format_threads(items)
        if "file" in first and "line" in first and "id" in first:
            return _format_breakpoints(items)
    # Generic list
    lines = []
    for i, item in enumerate(items):
        if isinstance(item, dict):
            lines.append(f"  [{i}] {_format_dict_inline(item)}")
        else:
            lines.append(f"  [{i}] {item}")
    return "\n".join(lines)


def _format_dict(d: dict[str, Any]) -> str:
    """Format a dict as CLI key-value pairs."""
    if not d:
        return "(empty)"
    # Known dict shapes
    if "expression" in d and ("value" in d or "result" in d or "status" in d):
        return _format_eval_result(d)
    # Generic dict
    lines = []
    max_key = max(len(str(k)) for k in d) if d else 0
    for k, v in d.items():
        if isinstance(v, (dict, list)):
            lines.append(f"  {k:<{max_key}}  {json.dumps(v, default=str)}")
        else:
            lines.append(f"  {k:<{max_key}}  {v}")
    return "\n".join(lines)


def _format_dict_inline(d: dict[str, Any]) -> str:
    """Format a dict on a single line."""
    parts = [f"{k}={v}" for k, v in d.items() if v is not None]
    return ", ".join(parts)


def _format_stack_frames(frames: list[dict[str, Any]]) -> str:
    """Format stack trace as a readable call stack."""
    lines = []
    for i, f in enumerate(frames):
        method = f.get("method_name") or f.get("method") or "??"
        file = f.get("file") or "??"
        line = f.get("line", "?")
        module = f.get("module") or ""
        prefix = "→ " if i == 0 else "  "
        loc = f"{file}:{line}"
        if module:
            loc += f"  [{module}]"
        lines.append(f"  {prefix}#{i:<3} {method}")
        lines.append(f"         at {loc}")
    return "\n".join(lines)


def _format_variables(variables: list[dict[str, Any]]) -> str:
    """Format variables as name = value (type)."""
    if not variables:
        return "(no variables)"
    lines = []
    max_name = max(len(v.get("name", "")) for v in variables)
    for v in variables:
        name = v.get("name", "?")
        value = v.get("value", "??")
        typ = v.get("type_name") or v.get("type") or ""
        children = " [+]" if v.get("has_children") or v.get("hasChildren") else ""
        type_str = f"  ({typ})" if typ else ""
        lines.append(f"  {name:<{max_name}}  = {value}{type_str}{children}")
    return "\n".join(lines)


def _format_threads(threads: list[dict[str, Any]]) -> str:
    """Format thread list."""
    lines = []
    for t in threads:
        tid = t.get("thread_id") or t.get("id", "?")
        name = t.get("name") or "unnamed"
        state = t.get("state", "unknown")
        main = " (main)" if t.get("is_main") or t.get("isMain") else ""
        lines.append(f"  [{tid}] {name} — {state}{main}")
    return "\n".join(lines)


def _format_breakpoints(breakpoints: list[dict[str, Any]]) -> str:
    """Format breakpoint list."""
    lines = []
    for bp in breakpoints:
        bp_id = bp.get("id", "?")
        file = bp.get("file", "?")
        line = bp.get("line", "?")
        enabled = "✓" if bp.get("enabled", True) else "✗"
        cond = bp.get("condition")
        cond_str = f"  when {cond}" if cond else ""
        lines.append(f"  {enabled} {bp_id}  {file}:{line}{cond_str}")
    return "\n".join(lines)


def _format_eval_result(d: dict[str, Any]) -> str:
    """Format expression evaluation result."""
    expr = d.get("expression", "?")
    status = d.get("status", "?")
    value = d.get("value") or d.get("result") or ""
    typ = d.get("type") or d.get("type_name") or ""
    error = d.get("error")

    if error:
        return f"  {expr}  →  error: {error}"
    type_str = f"  ({typ})" if typ else ""
    return f"  {expr}  =  {value}{type_str}  [{status}]"


class RiderMCPServer:
    """MCP Server wrapping the Rider debug middleware."""

    def __init__(self) -> None:
        self.server = Server("rider-debug-mcp")
        self.client = RiderClient()
        self.session = SessionManager()
        self.report_gen = ReportGenerator()
        self.crash_analyzer = CrashAnalyzer(self.client, self.session, self.report_gen)
        self.router = create_router(self.client, self.session, self.crash_analyzer)
        self.parser = CommandParser()

        self._register_tools()

    def _register_tools(self) -> None:
        """Register MCP tools."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="rider_cli",
                    description=RIDER_CLI_DESCRIPTION,
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "CLI command(s), one per line.",
                            }
                        },
                        "required": ["command"],
                    },
                ),
                Tool(
                    name="rider_query",
                    description=RIDER_QUERY_DESCRIPTION,
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Query string.",
                            }
                        },
                        "required": ["query"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            if name == "rider_cli":
                return await self._handle_cli(arguments.get("command", ""))
            elif name == "rider_query":
                return await self._handle_query(arguments.get("query", ""))
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async def _handle_cli(self, command_text: str) -> list[TextContent]:
        """Handle rider_cli tool invocation."""
        try:
            commands = self.parser.parse_batch(command_text)
        except ParseError as exc:
            return [TextContent(type="text", text=f"Parse error: {exc}")]

        try:
            results = await self.router.dispatch_batch(commands)
        except RiderConnectionError as exc:
            return [TextContent(type="text", text=f"Connection error: {exc}")]

        output_parts = []
        for cmd, result in zip(commands, results):
            status_icon = "✓" if result.status == CommandStatus.SUCCESS else "✗"
            msg = result.message or ""
            line = f"{status_icon} {cmd.name}: {msg}"
            if result.data is not None:
                line += f"\n{_format_result(result.data)}"
            output_parts.append(line)

        return [TextContent(type="text", text="\n\n".join(output_parts))]

    async def _handle_query(self, query_text: str) -> list[TextContent]:
        """Handle rider_query tool invocation."""
        query = query_text.strip()
        parts = query.split(maxsplit=1)
        query_cmd = parts[0].lower() if parts else ""
        query_arg = parts[1] if len(parts) > 1 else None

        if query_cmd == "help":
            return self._query_help(query_arg)
        elif query_cmd == "context":
            ctx = self.session.get_context()
            return [TextContent(type="text", text=_format_result(ctx))]
        elif query_cmd == "crash_report":
            report = self.crash_analyzer.get_latest_report()
            if report is None:
                return [TextContent(type="text", text="No crash reports available.")]
            return [TextContent(type="text", text=_format_result(report.model_dump()))]
        elif query_cmd == "crash_history":
            reports = self.crash_analyzer.get_history()
            data = [{"report_id": r.report_id, "summary": r.summary, "timestamp": r.timestamp} for r in reports]
            return [TextContent(type="text", text=_format_result(data))]
        elif query_cmd == "breakpoints":
            bps = [bp.model_dump() for bp in self.session.breakpoints]
            return [TextContent(type="text", text=_format_result(bps))]
        elif query_cmd == "health":
            try:
                health = await self.client.health_check()
            except Exception as exc:
                health = {"connected": False, "error": str(exc)}
            return [TextContent(type="text", text=_format_result(health))]
        else:
            return [TextContent(
                type="text",
                text=f"Unknown query: {query_cmd}\n\nAvailable queries: help, context, crash_report, crash_history, breakpoints, health",
            )]

    def _query_help(self, command_name: str | None = None) -> list[TextContent]:
        """Return help text."""
        from rider_debug_mcp.middleware.help import get_help_text

        text = get_help_text(self.router, command_name)
        return [TextContent(type="text", text=text)]

    async def run(self) -> None:
        """Run the MCP server with stdio transport."""
        # Try to connect to Rider (non-fatal if it fails)
        try:
            await self.client.connect()
            logger.info("Connected to Rider IDE")
        except RiderConnectionError as exc:
            logger.warning("Could not connect to Rider: %s (will retry on first command)", exc)

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, self.server.create_initialization_options())
