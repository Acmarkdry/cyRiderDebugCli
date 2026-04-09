"""Entry point for running the MCP server: python -m rider_debug_mcp."""

import asyncio
import logging

from rider_debug_mcp.server import RiderMCPServer


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    server = RiderMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
