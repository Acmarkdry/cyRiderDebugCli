"""Unit tests for MCP server tool registration and routing."""

from __future__ import annotations

import pytest

from rider_debug_mcp.server import RiderMCPServer


class TestRiderMCPServer:
    def test_server_creation(self):
        server = RiderMCPServer()
        assert server.server is not None
        assert server.parser is not None
        assert server.router is not None

    def test_router_has_all_commands(self):
        server = RiderMCPServer()
        cmds = server.router.registered_commands
        # Breakpoint commands
        assert "add_breakpoint" in cmds
        assert "remove_breakpoint" in cmds
        assert "list_breakpoints" in cmds
        assert "clear_breakpoints" in cmds
        # Debug commands
        assert "start_debug" in cmds
        assert "stop_debug" in cmds
        assert "step_over" in cmds
        # Inspect commands
        assert "get_variables" in cmds
        assert "evaluate" in cmds
        assert "get_stack_trace" in cmds
        assert "get_threads" in cmds
        # Analysis commands
        assert "analyze_crash" in cmds
        assert "crash_report" in cmds
        assert "crash_history" in cmds

    @pytest.mark.asyncio
    async def test_handle_cli_parse_error(self):
        server = RiderMCPServer()
        result = await server._handle_cli("")
        assert len(result) == 1
        assert "Parse error" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_query_help(self):
        server = RiderMCPServer()
        result = await server._handle_query("help")
        assert len(result) == 1
        assert "Available Commands" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_query_help_specific(self):
        server = RiderMCPServer()
        result = await server._handle_query("help add_breakpoint")
        assert len(result) == 1
        assert "add_breakpoint" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_query_unknown(self):
        server = RiderMCPServer()
        result = await server._handle_query("unknown_query")
        assert len(result) == 1
        assert "Unknown query" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_query_context(self):
        server = RiderMCPServer()
        result = await server._handle_query("context")
        assert len(result) == 1
        # Should return session context (even if empty)
        assert "session" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_query_breakpoints(self):
        server = RiderMCPServer()
        result = await server._handle_query("breakpoints")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_handle_query_crash_report_empty(self):
        server = RiderMCPServer()
        result = await server._handle_query("crash_report")
        assert "No crash reports" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_query_crash_history_empty(self):
        server = RiderMCPServer()
        result = await server._handle_query("crash_history")
        assert len(result) == 1
