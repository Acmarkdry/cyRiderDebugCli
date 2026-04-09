"""Unit tests for SessionManager."""

from rider_debug_mcp.gateway.models import Breakpoint, DebugSessionStatus
from rider_debug_mcp.middleware.session import SessionManager


class TestSessionLifecycle:
    def test_start_session(self):
        sm = SessionManager()
        session = sm.start_session("MyApp")
        assert session.status == DebugSessionStatus.RUNNING
        assert session.configuration_name == "MyApp"
        assert sm.is_active is True

    def test_stop_session(self):
        sm = SessionManager()
        sm.start_session()
        sm.stop_session()
        assert sm.current_session is None
        assert sm.is_active is False

    def test_pause_resume(self):
        sm = SessionManager()
        sm.start_session()
        sm.pause_session()
        assert sm.current_session.status == DebugSessionStatus.PAUSED
        sm.resume_session()
        assert sm.current_session.status == DebugSessionStatus.RUNNING

    def test_no_session(self):
        sm = SessionManager()
        assert sm.current_session is None
        assert sm.is_active is False


class TestBreakpointCache:
    def test_cache_breakpoint(self):
        sm = SessionManager()
        bp = Breakpoint(id="bp-1", file="Player.cs", line=42)
        sm.cache_breakpoint(bp)
        assert sm.breakpoint_count == 1
        assert sm.get_breakpoint("bp-1") == bp

    def test_remove_breakpoint(self):
        sm = SessionManager()
        bp = Breakpoint(id="bp-1", file="Player.cs", line=42)
        sm.cache_breakpoint(bp)
        removed = sm.remove_breakpoint("bp-1")
        assert removed == bp
        assert sm.breakpoint_count == 0
        assert sm.get_breakpoint("bp-1") is None

    def test_remove_nonexistent(self):
        sm = SessionManager()
        removed = sm.remove_breakpoint("nonexistent")
        assert removed is None

    def test_clear_breakpoints(self):
        sm = SessionManager()
        sm.cache_breakpoint(Breakpoint(id="bp-1", file="F.cs", line=1))
        sm.cache_breakpoint(Breakpoint(id="bp-2", file="F.cs", line=2))
        count = sm.clear_breakpoints()
        assert count == 2
        assert sm.breakpoint_count == 0

    def test_breakpoints_list(self):
        sm = SessionManager()
        sm.cache_breakpoint(Breakpoint(id="bp-1", file="F.cs", line=1))
        sm.cache_breakpoint(Breakpoint(id="bp-2", file="F.cs", line=2))
        assert len(sm.breakpoints) == 2

    def test_update_existing_breakpoint(self):
        sm = SessionManager()
        bp1 = Breakpoint(id="bp-1", file="F.cs", line=1, enabled=True)
        sm.cache_breakpoint(bp1)
        bp2 = Breakpoint(id="bp-1", file="F.cs", line=1, enabled=False)
        sm.cache_breakpoint(bp2)
        assert sm.breakpoint_count == 1
        assert sm.get_breakpoint("bp-1").enabled is False


class TestOperationHistory:
    def test_history_recording(self):
        sm = SessionManager()
        sm.start_session()
        sm.cache_breakpoint(Breakpoint(id="bp-1", file="F.cs", line=1))
        history = sm.history
        assert len(history) >= 2
        ops = [h["operation"] for h in history]
        assert "session_start" in ops
        assert "breakpoint_cached" in ops

    def test_history_limit(self):
        sm = SessionManager(max_history=3)
        for i in range(5):
            sm.record_operation(f"op_{i}")
        assert len(sm.history) == 3

    def test_custom_operation(self):
        sm = SessionManager()
        sm.record_operation("custom_op", {"key": "value"})
        assert sm.history[-1]["operation"] == "custom_op"
        assert sm.history[-1]["details"] == {"key": "value"}


class TestContextQuery:
    def test_context_with_session(self):
        sm = SessionManager()
        sm.start_session("MyApp")
        sm.cache_breakpoint(Breakpoint(id="bp-1", file="F.cs", line=1))
        ctx = sm.get_context()
        assert ctx["session"] is not None
        assert ctx["breakpoint_count"] == 1
        assert len(ctx["breakpoints"]) == 1
        assert len(ctx["recent_operations"]) > 0

    def test_context_without_session(self):
        sm = SessionManager()
        ctx = sm.get_context()
        assert ctx["session"] is None
        assert ctx["breakpoint_count"] == 0
