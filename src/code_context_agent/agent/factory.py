"""Agent factory for creating configured analysis agents.

This module provides functions to create strands Agent instances
configured with the appropriate tools and system prompts.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from strands import Agent
from strands.models import BedrockModel

from ..config import get_settings
from .sop import DEEP_PROMPT, FAST_PROMPT


def get_analysis_tools() -> list[Any]:
    """Get the list of tools for code analysis.

    Returns:
        List of tool functions for the agent.
    """
    # Import tools here to avoid circular imports
    # Import graph from strands_tools, but use custom shell for proper STDIO capture
    from strands_tools import graph

    from ..tools import (
        astgrep_inline_rule,
        astgrep_scan,
        astgrep_scan_rule_pack,
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
        repomix_orientation,
        rg_search,
        write_file_list,
    )
    from ..tools.graph import (
        code_graph_analyze,
        code_graph_create,
        code_graph_explore,
        code_graph_export,
        code_graph_ingest_astgrep,
        code_graph_ingest_lsp,
        code_graph_load,
        code_graph_save,
        code_graph_stats,
    )
    from ..tools.graph.tools import code_graph_ingest_inheritance, code_graph_ingest_rg, code_graph_ingest_tests
    from ..tools.lsp import (
        lsp_definition,
        lsp_document_symbols,
        lsp_hover,
        lsp_references,
        lsp_shutdown,
        lsp_start,
    )
    from ..tools.shell_tool import shell

    return [
        # Discovery tools
        create_file_manifest,
        repomix_orientation,
        repomix_bundle,
        rg_search,
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
        # LSP tools
        lsp_start,
        lsp_document_symbols,
        lsp_hover,
        lsp_references,
        lsp_definition,
        lsp_shutdown,
        # ast-grep tools (rule packs + ad-hoc + inline)
        astgrep_scan,
        astgrep_scan_rule_pack,
        astgrep_inline_rule,
        # Shell for custom commands
        shell,
        # Code graph analysis
        code_graph_create,
        code_graph_ingest_lsp,
        code_graph_ingest_astgrep,
        code_graph_ingest_rg,
        code_graph_ingest_inheritance,
        code_graph_ingest_tests,
        code_graph_analyze,
        code_graph_explore,
        code_graph_export,
        code_graph_save,
        code_graph_load,
        code_graph_stats,
        # Multi-agent DAG orchestration
        graph,
    ]


def _get_steering_hooks() -> list[Any]:
    """Get optional steering hooks for progressive disclosure.

    Returns:
        List of steering handlers, or empty list if steering unavailable.
    """
    try:
        from .steering import STEERING_AVAILABLE, create_all_steering_handlers

        if STEERING_AVAILABLE:
            return create_all_steering_handlers()
    except ImportError:
        pass
    return []


def create_agent(
    mode: str = "fast",
    use_steering: bool = True,
) -> Agent:
    """Create a configured agent for code context analysis.

    Args:
        mode: Analysis mode - "fast" or "deep".
        use_steering: Enable experimental steering for progressive disclosure.
            When enabled, the agent receives contextual guidance at key points
            (before tool calls, before output) rather than loading all rules upfront.

    Returns:
        Configured Agent instance ready for analysis.

    Example:
        >>> agent = create_agent(mode="fast")
        >>> response = await agent.stream_async("Analyze /path/to/repo")
    """
    settings = get_settings()

    # Mode-specific thinking budget: FAST=8000, DEEP=20000
    thinking_budget = 8000 if mode.lower() == "fast" else 20000

    logger.info(
        f"Creating agent: mode={mode}, model={settings.model_id}, "
        f"region={settings.region}, thinking_budget={thinking_budget}, "
        f"steering={'enabled' if use_steering else 'disabled'}",
    )

    # Create Bedrock model with extended thinking and 1M context enabled
    model = BedrockModel(
        model_id=settings.model_id,
        region_name=settings.region,
        temperature=settings.temperature,
        additional_request_fields={
            "thinking": {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            },
            # Enable 1M context window (beta feature for Sonnet 4 and 4.5)
            "anthropic_beta": ["context-1m-2025-08-07"],
        },
    )

    # Select system prompt based on mode
    system_prompt = DEEP_PROMPT if mode.lower() == "deep" else FAST_PROMPT

    # Get tools
    tools = get_analysis_tools()

    # Get optional steering hooks
    hooks = _get_steering_hooks() if use_steering else []
    if hooks:
        logger.info(f"Steering enabled with {len(hooks)} hooks")

    logger.info(f"Agent configured with {len(tools)} tools")

    return Agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        hooks=hooks if hooks else None,
        callback_handler=None,  # We use stream_async for events
    )
