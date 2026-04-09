"""Command handlers - breakpoint, debug, inspect, and analysis handlers."""

from rider_debug_mcp.analysis.crash import CrashAnalyzer
from rider_debug_mcp.gateway.client import RiderClient
from rider_debug_mcp.handlers.analysis import AnalysisHandler
from rider_debug_mcp.handlers.breakpoint import BreakpointHandler
from rider_debug_mcp.handlers.debug import DebugHandler
from rider_debug_mcp.handlers.inspect import InspectHandler
from rider_debug_mcp.middleware.router import CommandRouter
from rider_debug_mcp.middleware.session import SessionManager


def create_router(
    client: RiderClient,
    session: SessionManager,
    crash_analyzer: CrashAnalyzer,
) -> CommandRouter:
    """Create a fully configured CommandRouter with all handlers registered.

    Args:
        client: The Rider gateway client.
        session: The session manager.
        crash_analyzer: The crash analysis engine.

    Returns:
        A :class:`CommandRouter` with all handlers registered.
    """
    router = CommandRouter()
    router.register(BreakpointHandler(client, session))
    router.register(DebugHandler(client, session))
    router.register(InspectHandler(client))
    router.register(AnalysisHandler(crash_analyzer))
    return router
