"""Agent factory for creating configured analysis agents.

This module provides functions to create strands Agent instances
configured with the appropriate tools, system prompt, hooks, and
structured output model.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..config import get_settings


def get_analysis_tools() -> list[Any]:
    """Get the list of tools for code analysis.

    Returns:
        List of tool functions and MCP tool providers for the agent.
    """
    # Import tools here to avoid circular imports
    # Import graph from strands_tools for multi-agent DAG orchestration
    from strands_tools import graph

    from ..tools import (
        create_file_manifest,
        git_blame_summary,
        git_contributors,
        git_diff_file,
        git_file_history,
        git_files_changed_together,
        git_hotspots,
        git_recent_commits,
        read_file_bounded,
        repomix_bundle,
        repomix_bundle_with_context,
        repomix_compressed_signatures,
        repomix_json_export,
        repomix_orientation,
        repomix_split_bundle,
        rg_search,
        write_file,
        write_file_list,
    )
    from ..tools.search.tools import bm25_search
    from ..tools.shell_tool import shell

    tools: list[Any] = [
        # Discovery tools
        create_file_manifest,
        repomix_orientation,
        repomix_bundle,
        repomix_bundle_with_context,
        repomix_compressed_signatures,
        repomix_json_export,
        repomix_split_bundle,
        rg_search,
        bm25_search,
        write_file,
        write_file_list,
        read_file_bounded,
        # Git history tools (coupling, evolution, authorship)
        git_files_changed_together,
        git_file_history,
        git_recent_commits,
        git_diff_file,
        git_blame_summary,
        git_hotspots,
        git_contributors,
        # Shell for custom commands
        shell,
        # Multi-agent DAG orchestration
        graph,
    ]

    # Add GitNexus MCP server for structural code intelligence
    gitnexus_provider = _create_gitnexus_provider()
    if gitnexus_provider is not None:
        tools.append(gitnexus_provider)

    # Add context7 MCP server for library documentation lookup
    context7_provider = _create_context7_provider()
    if context7_provider is not None:
        tools.append(context7_provider)

    return tools


def _create_gitnexus_provider() -> Any | None:
    """Create an MCPClient for the GitNexus code intelligence server.

    Returns the MCPClient (a ToolProvider that the Agent handles natively),
    or None if GitNexus is disabled or npx is not available.
    """
    settings = get_settings()
    if not settings.gitnexus_enabled:
        logger.info("GitNexus MCP server disabled via settings")
        return None

    import shutil

    if not shutil.which("npx"):
        logger.warning("npx not found, skipping GitNexus MCP server")
        return None

    try:
        from mcp import StdioServerParameters, stdio_client
        from strands.tools.mcp import MCPClient

        gitnexus = MCPClient(
            lambda: stdio_client(
                StdioServerParameters(
                    command="npx",
                    args=["gitnexus", "mcp"],
                ),
            ),
            prefix="gitnexus",
        )
        logger.info("GitNexus MCP server configured (tools will be prefixed with 'gitnexus_')")
    except (ImportError, Exception) as e:  # noqa: BLE001
        logger.warning(f"Failed to configure GitNexus MCP server: {e}")
        return None
    else:
        return gitnexus


def _create_context7_provider() -> Any | None:
    """Create an MCPClient for the context7 documentation server.

    Returns the MCPClient (a ToolProvider that the Agent handles natively),
    or None if context7 is disabled or npx is not available.
    """
    settings = get_settings()
    if not settings.context7_enabled:
        logger.info("context7 MCP server disabled via settings")
        return None

    import shutil

    if not shutil.which("npx"):
        logger.warning("npx not found, skipping context7 MCP server")
        return None

    try:
        from mcp import StdioServerParameters, stdio_client
        from strands.tools.mcp import MCPClient

        context7 = MCPClient(
            lambda: stdio_client(
                StdioServerParameters(
                    command="npx",
                    args=["-y", "@upstash/context7-mcp@1"],
                ),
            ),
            prefix="context7",
        )
        logger.info("context7 MCP server configured (tools will be prefixed with 'context7_')")
    except (ImportError, Exception) as e:  # noqa: BLE001
        logger.warning(f"Failed to configure context7 MCP server: {e}")
        return None
    else:
        return context7
