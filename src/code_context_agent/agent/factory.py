"""Agent factory for creating configured analysis agents.

This module provides functions to create strands Agent instances
configured with the appropriate tools and system prompts.
"""

from __future__ import annotations

import logging
from typing import Any

from strands import Agent
from strands.models import BedrockModel

from ..config import get_settings
from .sop import DEEP_MODE_SOP, FAST_MODE_SOP

logger = logging.getLogger(__name__)


def get_analysis_tools() -> list[Any]:
    """Get the list of tools for code analysis.

    Returns:
        List of tool functions for the agent.
    """
    # Import tools here to avoid circular imports
    # Import shell and graph from strands_tools
    from strands_tools import graph, shell

    from ..tools import (
        astgrep_scan,
        astgrep_scan_rule_pack,
        create_file_manifest,
        read_file_bounded,
        repomix_bundle,
        repomix_orientation,
        rg_search,
        write_file_list,
    )
    from ..tools.lsp import (
        lsp_definition,
        lsp_document_symbols,
        lsp_hover,
        lsp_references,
        lsp_shutdown,
        lsp_start,
    )

    return [
        # Discovery tools
        create_file_manifest,
        repomix_orientation,
        repomix_bundle,
        rg_search,
        write_file_list,
        read_file_bounded,
        # LSP tools
        lsp_start,
        lsp_document_symbols,
        lsp_hover,
        lsp_references,
        lsp_definition,
        lsp_shutdown,
        # ast-grep tools
        astgrep_scan,
        astgrep_scan_rule_pack,
        # Shell for custom commands
        shell,
        # Graph visualization
        graph,
    ]


def create_agent(mode: str = "fast") -> Agent:
    """Create a configured agent for code context analysis.

    Args:
        mode: Analysis mode - "fast" or "deep".

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
        f"region={settings.region}, thinking_budget={thinking_budget}"
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
    system_prompt = DEEP_MODE_SOP if mode.lower() == "deep" else FAST_MODE_SOP

    # Get tools
    tools = get_analysis_tools()

    logger.info(f"Agent configured with {len(tools)} tools")

    return Agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        callback_handler=None,  # We use stream_async for events
    )
