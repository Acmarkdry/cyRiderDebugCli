"""Debug event models for Rider event stream."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from rider_debug_mcp.gateway.models import StackFrame


class DebugEventType(str, Enum):
    """Types of debug events."""

    BREAKPOINT_HIT = "breakpoint_hit"
    EXCEPTION = "exception"
    PROCESS_EXIT = "process_exit"


class BreakpointHitEvent(BaseModel):
    """Event fired when a breakpoint is hit."""

    event_type: Literal[DebugEventType.BREAKPOINT_HIT] = DebugEventType.BREAKPOINT_HIT
    breakpoint_id: str = Field(description="ID of the breakpoint that was hit")
    file: str = Field(description="Source file where breakpoint was hit")
    line: int = Field(ge=1, description="Line number of the breakpoint")
    thread_id: int = Field(description="Thread that hit the breakpoint")
    stack_frame: StackFrame | None = Field(default=None, description="Top stack frame at breakpoint")
    timestamp: str = Field(description="Event timestamp (ISO 8601)")


class ExceptionEvent(BaseModel):
    """Event fired when an exception occurs during debugging."""

    event_type: Literal[DebugEventType.EXCEPTION] = DebugEventType.EXCEPTION
    exception_type: str = Field(description="Fully qualified exception type name")
    message: str = Field(description="Exception message")
    stack_trace: str | None = Field(default=None, description="Raw stack trace string")
    is_unhandled: bool = Field(default=True, description="Whether the exception is unhandled")
    thread_id: int = Field(description="Thread where exception occurred")
    timestamp: str = Field(description="Event timestamp (ISO 8601)")


class ProcessExitEvent(BaseModel):
    """Event fired when the debugged process exits."""

    event_type: Literal[DebugEventType.PROCESS_EXIT] = DebugEventType.PROCESS_EXIT
    exit_code: int = Field(description="Process exit code")
    is_abnormal: bool = Field(default=False, description="Whether the exit was abnormal (non-zero)")
    timestamp: str = Field(description="Event timestamp (ISO 8601)")


# Union type for all debug events
DebugEvent = Annotated[
    BreakpointHitEvent | ExceptionEvent | ProcessExitEvent,
    Field(discriminator="event_type"),
]


# ---------------------------------------------------------------------------
# EventListener – WebSocket-based debug event stream consumer
# ---------------------------------------------------------------------------

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import websockets
import websockets.exceptions

logger = logging.getLogger(__name__)

EventCallback = Callable[[BreakpointHitEvent | ExceptionEvent | ProcessExitEvent], Coroutine[Any, Any, None]]

_EVENT_MODEL_MAP: dict[str, type[BaseModel]] = {
    DebugEventType.BREAKPOINT_HIT: BreakpointHitEvent,
    DebugEventType.EXCEPTION: ExceptionEvent,
    DebugEventType.PROCESS_EXIT: ProcessExitEvent,
}


class EventListener:
    """Listens to Rider debug events via WebSocket.

    Supports automatic reconnection with exponential backoff.
    """

    MAX_RETRIES = 5
    BASE_DELAY = 1.0  # seconds

    def __init__(self, url: str = "ws://localhost:63342/api/debug/events") -> None:
        self._url = url
        self._callbacks: list[EventCallback] = []
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def on_event(self, callback: EventCallback) -> None:
        """Register a callback for debug events."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start listening in the background."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _listen_loop(self) -> None:
        """Main loop with reconnection and exponential backoff."""
        retries = 0
        while self._running:
            try:
                async for event in self._connect_and_stream():
                    retries = 0  # reset on successful event
                    for cb in self._callbacks:
                        try:
                            await cb(event)
                        except Exception:
                            logger.exception("Error in event callback")
            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException,
                OSError,
            ) as exc:
                if not self._running:
                    break
                retries += 1
                if retries > self.MAX_RETRIES:
                    logger.error("Max reconnection retries (%d) reached. Stopping.", self.MAX_RETRIES)
                    self._running = False
                    break
                delay = self.BASE_DELAY * (2 ** (retries - 1))
                logger.warning("WebSocket disconnected (%s). Reconnecting in %.1fs (retry %d/%d)", exc, delay, retries, self.MAX_RETRIES)
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break

    async def _connect_and_stream(self) -> AsyncIterator[BreakpointHitEvent | ExceptionEvent | ProcessExitEvent]:
        """Connect to WebSocket and yield parsed events."""
        async with websockets.connect(self._url) as ws:
            logger.info("Connected to event stream: %s", self._url)
            async for message in ws:
                try:
                    data = json.loads(message)
                    event = self._parse_event(data)
                    if event is not None:
                        yield event
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning("Failed to parse event message: %s", exc)

    @staticmethod
    def _parse_event(data: dict[str, Any]) -> BreakpointHitEvent | ExceptionEvent | ProcessExitEvent | None:
        """Parse a raw JSON dict into a typed event model."""
        event_type = data.get("event_type") or data.get("eventType")
        if event_type is None:
            logger.warning("Event missing event_type field: %s", data)
            return None

        model_cls = _EVENT_MODEL_MAP.get(event_type)
        if model_cls is None:
            logger.warning("Unknown event type: %s", event_type)
            return None

        return model_cls.model_validate(data)
