"""MCP server exposing code-context-agent's core analysis capabilities.

Provides tools for codebase analysis, code graph querying, and access
to analysis artifacts via the Model Context Protocol.
"""

from .server import mcp

__all__ = ["mcp"]
