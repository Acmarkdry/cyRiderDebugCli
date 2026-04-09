"""Unit tests for EventListener."""

import pytest

from rider_debug_mcp.gateway.events import (
    BreakpointHitEvent,
    EventListener,
    ExceptionEvent,
    ProcessExitEvent,
)


class TestEventListenerParsing:
    def test_parse_breakpoint_hit(self):
        data = {
            "event_type": "breakpoint_hit",
            "breakpoint_id": "bp-1",
            "file": "Player.cs",
            "line": 42,
            "thread_id": 1,
            "timestamp": "2025-01-01T00:00:00Z",
        }
        event = EventListener._parse_event(data)
        assert isinstance(event, BreakpointHitEvent)
        assert event.breakpoint_id == "bp-1"

    def test_parse_exception(self):
        data = {
            "event_type": "exception",
            "exception_type": "System.NullReferenceException",
            "message": "Object reference not set",
            "is_unhandled": True,
            "thread_id": 1,
            "timestamp": "2025-01-01T00:00:00Z",
        }
        event = EventListener._parse_event(data)
        assert isinstance(event, ExceptionEvent)
        assert event.exception_type == "System.NullReferenceException"

    def test_parse_process_exit(self):
        data = {
            "event_type": "process_exit",
            "exit_code": 1,
            "is_abnormal": True,
            "timestamp": "2025-01-01T00:00:00Z",
        }
        event = EventListener._parse_event(data)
        assert isinstance(event, ProcessExitEvent)
        assert event.exit_code == 1
        assert event.is_abnormal is True

    def test_parse_unknown_event_type(self):
        data = {"event_type": "unknown_type", "timestamp": "2025-01-01T00:00:00Z"}
        event = EventListener._parse_event(data)
        assert event is None

    def test_parse_missing_event_type(self):
        data = {"some_field": "value"}
        event = EventListener._parse_event(data)
        assert event is None

    def test_parse_camel_case_event_type(self):
        """Test that camelCase eventType is also recognized."""
        data = {
            "eventType": "process_exit",
            "exit_code": 0,
            "timestamp": "2025-01-01T00:00:00Z",
        }
        event = EventListener._parse_event(data)
        assert isinstance(event, ProcessExitEvent)


class TestEventListenerLifecycle:
    def test_init(self):
        listener = EventListener()
        assert listener._running is False
        assert listener._callbacks == []

    def test_register_callback(self):
        listener = EventListener()

        async def dummy_callback(event):
            pass

        listener.on_event(dummy_callback)
        assert len(listener._callbacks) == 1

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        listener = EventListener()
        await listener.stop()  # should not raise
        assert listener._running is False
