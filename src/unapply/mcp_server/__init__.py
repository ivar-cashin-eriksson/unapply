"""The MCP server for a job's matching agent: consent-scoped, anonymised reads.

`build_server` makes the server for one job; `AgentTools` holds the reads and the
consent checks behind its tools.
"""

from unapply.mcp_server.server import build_server
from unapply.mcp_server.tools import AgentTools, ToolRefused

__all__ = ["AgentTools", "ToolRefused", "build_server"]
