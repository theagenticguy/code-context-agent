"""Coordinator Agent factory for team-based code analysis.

The coordinator is a regular strands Agent (not a Swarm node) that dispatches
specialist Swarm teams via the dispatch_team tool. Teams execute in
parallel via ConcurrentToolExecutor.

Architecture:
    Enhanced Index (deterministic) → Coordinator Agent (LLM)
        ├── dispatch_team("team-structure", ...) ┐
        ├── dispatch_team("team-history", ...)    ├ parallel
        └── dispatch_team("team-reader", ...)     ┘
            → read_team_findings → write_bundle → AnalysisResult
"""

from __future__ import annotations

import json as _json
from typing import TYPE_CHECKING, Any

from loguru import logger
from strands import Agent
from strands.models import BedrockModel

from ..config import get_settings
from ..models.output import AnalysisResult

if TYPE_CHECKING:
    from pathlib import Path

    from strands.hooks import HookProvider


def _create_model() -> BedrockModel:
    """Create a BedrockModel configured for the coordinator agent."""
    from botocore.config import Config as BotoConfig

    settings = get_settings()
    return BedrockModel(
        model_id=settings.model_id,
        region_name=settings.region,
        temperature=settings.temperature,
        boto_client_config=BotoConfig(read_timeout=600, retries={"max_attempts": 10, "mode": "adaptive"}),
        additional_request_fields={
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": settings.full_reasoning_effort},
            "anthropic_beta": ["context-1m-2025-08-07"],
        },
    )


def _render_coordinator_prompt(
    repo_path: Path,
    output_dir: Path,
    heuristic: dict[str, Any],
    focus: str | None = None,
) -> str:
    """Render the lean coordinator system prompt from Jinja2 template."""
    from ..templates import render_prompt

    # Build a namespace object for the template to access heuristic fields via dot notation.
    # Supports __len__/__iter__ so Jinja2 filters (| length, | join) work on nested dicts.
    class _DictProxy:
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = data
            for key, value in data.items():
                if isinstance(value, dict):
                    setattr(self, key, _DictProxy(value))
                else:
                    setattr(self, key, value)

        def __getattr__(self, name: str) -> Any:
            return 0  # Safe fallback for missing keys in template

        def __len__(self) -> int:
            return len(self._data)

        def __iter__(self):
            return iter(self._data)

    return render_prompt(
        "coordinator.md.j2",
        repo_path=str(repo_path),
        output_dir=str(output_dir),
        heuristic=_DictProxy(heuristic),
        focus=focus,
    )


def _get_coordinator_tools(analysis_tools: list[Any]) -> list[Any]:
    """Get ALL tools for the coordinator agent.

    Includes:
    - 6 coordinator-specific tools (dispatch_team, read_team_findings,
      write_bundle, read_heuristic_summary, score_narrative, enrich_bundle)
    - All analysis tools (inherited by team agents via the swarm `tools` field)

    Args:
        analysis_tools: Pre-fetched list from get_analysis_tools().
    """
    from ..tools.coordinator_tools import (
        dispatch_team,
        enrich_bundle,
        read_heuristic_summary,
        read_team_findings,
        score_narrative,
        write_bundle,
    )

    return [
        dispatch_team,
        read_team_findings,
        write_bundle,
        read_heuristic_summary,
        score_narrative,
        enrich_bundle,
        *analysis_tools,
    ]


def create_coordinator_agent(
    repo_path: Path,
    output_dir: Path,
    focus: str | None = None,
    hooks: list[HookProvider] | None = None,
    *,
    team_execution_timeout: float,
    team_node_timeout: float,
) -> Agent:
    """Create a coordinator Agent that dispatches Swarm teams.

    The coordinator reads pre-computed index artifacts and uses the
    dispatch_team tool to dispatch specialist teams in parallel.

    Args:
        repo_path: Path to the repository.
        output_dir: Path to output directory with index artifacts.
        focus: Optional focus area for targeted analysis.
        hooks: Optional HookProviders for the coordinator.
        team_execution_timeout: Default max seconds for entire team swarm execution.
        team_node_timeout: Default max seconds per agent node within a team.

    Returns:
        Configured Agent ready for invocation.
    """
    # Get analysis tools (these are inherited by swarm team agents)
    from .factory import get_analysis_tools

    analysis_tools = get_analysis_tools()

    # Configure coordinator tools with output dir, repo path, and tool registry
    from ..tools.coordinator_tools import configure as configure_coordinator_tools

    configure_coordinator_tools(
        output_dir=output_dir,
        repo_path=repo_path,
        tools=analysis_tools,
        execution_timeout=team_execution_timeout,
        node_timeout=team_node_timeout,
    )

    # Load heuristic summary (preferred) or fall back to index metadata
    heuristic: dict[str, Any] = {}
    heuristic_path = output_dir / "heuristic_summary.json"
    metadata_path = output_dir / "index_metadata.json"

    if heuristic_path.exists():
        try:
            heuristic = _json.loads(heuristic_path.read_text())
            logger.info("Loaded heuristic summary for coordinator")
        except (OSError, ValueError) as e:
            logger.warning(f"Failed to load heuristic summary: {e}")

    if not heuristic and metadata_path.exists():
        try:
            raw = _json.loads(metadata_path.read_text())
            # Adapt index metadata to heuristic summary shape for template compatibility
            heuristic = {
                "volume": {
                    "total_files": raw.get("file_count", 0),
                    "languages": raw.get("languages", {}),
                    "frameworks": raw.get("frameworks", []),
                    "estimated_tokens": 0,
                },
                "symbols": {"functions": 0, "classes": 0, "modules": 0},
                "health": {
                    "semgrep_findings": {"critical": 0, "high": 0, "medium": 0},
                },
                "topology": {
                    "graph_nodes": raw.get("graph_stats", {}).get("node_count", 0),
                    "graph_edges": raw.get("graph_stats", {}).get("edge_count", 0),
                },
                "git": {},
            }
            logger.info("Loaded index metadata (fallback) for coordinator")
        except (OSError, ValueError) as e:
            logger.warning(f"Failed to load index metadata: {e}")

    # Render lean system prompt
    system_prompt = _render_coordinator_prompt(
        repo_path=repo_path,
        output_dir=output_dir,
        heuristic=heuristic,
        focus=focus,
    )

    # Create model and tools
    model = _create_model()
    tools = _get_coordinator_tools(analysis_tools)

    # Create the coordinator Agent
    from strands.agent.conversation_manager import SummarizingConversationManager

    conversation_manager = SummarizingConversationManager(
        summary_ratio=0.3,
        preserve_recent_messages=10,
    )

    agent = Agent(
        name="coordinator",
        system_prompt=system_prompt,
        model=model,
        tools=tools,
        structured_output_model=AnalysisResult,
        callback_handler=None,
        conversation_manager=conversation_manager,
    )

    # Apply hooks
    if hooks:
        for hook in hooks:
            agent.hooks.add_hook(hook)

    logger.info(
        f"Created coordinator agent with {len(tools)} tools, focus={focus}, repo={repo_path}",
    )

    return agent
