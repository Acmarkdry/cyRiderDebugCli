"""Session manager for tracking debug state."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from rider_debug_mcp.gateway.models import Breakpoint, DebugSession, DebugSessionStatus


class SessionManager:
    """Manages debug session state, breakpoint cache, and operation history.

    Attributes:
        max_history: Maximum number of recent operations to keep.
    """

    def __init__(self, max_history: int = 50) -> None:
        self.max_history = max_history
        self._session: DebugSession | None = None
        self._breakpoints: dict[str, Breakpoint] = {}
        self._history: deque[dict[str, Any]] = deque(maxlen=max_history)

    # --- Session lifecycle ---

    def start_session(self, configuration_name: str | None = None) -> DebugSession:
        """Start a new debug session."""
        self._session = DebugSession(
            session_id=str(uuid.uuid4()),
            status=DebugSessionStatus.RUNNING,
            configuration_name=configuration_name,
            start_time=datetime.now(UTC).isoformat(),
        )
        self._record("session_start", {"session_id": self._session.session_id})
        return self._session

    def stop_session(self) -> None:
        """Stop the current debug session."""
        if self._session:
            self._record("session_stop", {"session_id": self._session.session_id})
            self._session.status = DebugSessionStatus.STOPPED
            self._session = None

    def pause_session(self) -> None:
        """Mark the session as paused."""
        if self._session:
            self._session.status = DebugSessionStatus.PAUSED
            self._record("session_pause", {"session_id": self._session.session_id})

    def resume_session(self) -> None:
        """Mark the session as running."""
        if self._session:
            self._session.status = DebugSessionStatus.RUNNING
            self._record("session_resume", {"session_id": self._session.session_id})

    @property
    def current_session(self) -> DebugSession | None:
        """Return the current session, or ``None``."""
        return self._session

    @property
    def is_active(self) -> bool:
        """Return whether there is an active (non-stopped) session."""
        return self._session is not None and self._session.status != DebugSessionStatus.STOPPED

    # --- Breakpoint cache ---

    def cache_breakpoint(self, bp: Breakpoint) -> None:
        """Add or update a breakpoint in the cache."""
        self._breakpoints[bp.id] = bp
        self._record("breakpoint_cached", {"id": bp.id, "file": bp.file, "line": bp.line})

    def remove_breakpoint(self, bp_id: str) -> Breakpoint | None:
        """Remove a breakpoint from the cache."""
        bp = self._breakpoints.pop(bp_id, None)
        if bp:
            self._record("breakpoint_removed", {"id": bp_id})
        return bp

    def get_breakpoint(self, bp_id: str) -> Breakpoint | None:
        """Get a cached breakpoint by ID."""
        return self._breakpoints.get(bp_id)

    @property
    def breakpoints(self) -> list[Breakpoint]:
        """Return all cached breakpoints."""
        return list(self._breakpoints.values())

    @property
    def breakpoint_count(self) -> int:
        """Return the number of cached breakpoints."""
        return len(self._breakpoints)

    def clear_breakpoints(self) -> int:
        """Clear all cached breakpoints. Returns the count removed."""
        count = len(self._breakpoints)
        self._breakpoints.clear()
        self._record("breakpoints_cleared", {"count": count})
        return count

    # --- Operation history ---

    def _record(self, operation: str, details: dict[str, Any] | None = None) -> None:
        """Record an operation in the history."""
        self._history.append(
            {
                "operation": operation,
                "details": details or {},
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def record_operation(self, operation: str, details: dict[str, Any] | None = None) -> None:
        """Public interface to record a custom operation."""
        self._record(operation, details)

    @property
    def history(self) -> list[dict[str, Any]]:
        """Return the operation history (newest last)."""
        return list(self._history)

    # --- Context query ---

    def get_context(self) -> dict[str, Any]:
        """Return the full session context for ``rider_query context``."""
        return {
            "session": self._session.model_dump() if self._session else None,
            "breakpoints": [bp.model_dump() for bp in self._breakpoints.values()],
            "breakpoint_count": self.breakpoint_count,
            "recent_operations": list(self._history)[-10:],
        }
