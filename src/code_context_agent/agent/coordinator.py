"""Coordinator Agent factory for team-based code analysis.

The coordinator is a regular strands Agent (not a Swarm node) that dispatches
specialist Swarm teams via strands_tools.swarm tool calls. Teams execute in
parallel via ConcurrentToolExecutor.

Architecture:
    Enhanced Index (deterministic) → Coordinator Agent (LLM)
        ├── swarm(task=..., agents=[structure team]) ┐
        ├── swarm(task=..., agents=[history team])   ├ parallel
        └── swarm(task=..., agents=[reader team])    ┘
            → Consolidate findings → AnalysisResult
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
        boto_client_config=BotoConfig(read_timeout=600, retries={"max_attempts": 3, "mode": "adaptive"}),
        additional_request_fields={
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": settings.full_reasoning_effort},
            "anthropic_beta": ["context-1m-2025-08-07"],
        },
    )


def _render_coordinator_prompt(
    repo_path: Path,
    output_dir: Path,
    metadata: dict[str, Any],
    graph_summary: str,
    mode: str,
) -> str:
    """Render the coordinator system prompt from the Jinja2 template."""
    from ..templates import render_prompt

    # Build a namespace object for the template to access metadata fields via dot notation
    class _MetadataProxy:
        def __init__(self, data: dict[str, Any]) -> None:
            self.__dict__.update(data)

    return render_prompt(
        "coordinator.md.j2",
        repo_path=str(repo_path),
        output_dir=str(output_dir),
        metadata=_MetadataProxy(metadata),
        graph_summary=graph_summary,
        mode=mode,
    )


def _get_coordinator_tools() -> list[Any]:
    """Get ALL tools for the coordinator agent.

    Reuses get_analysis_tools() from factory.py and prepends the swarm
    dispatch tool. The coordinator registers every tool so that child
    swarm agents can inherit any subset via the `tools` field.
    """
    from strands_tools.swarm import swarm

    from .factory import get_analysis_tools

    return [swarm, *get_analysis_tools()]


def create_coordinator_agent(
    repo_path: Path,
    output_dir: Path,
    mode: str = "standard",
    hooks: list[HookProvider] | None = None,
) -> Agent:
    """Create a coordinator Agent that dispatches Swarm teams.

    The coordinator reads pre-computed index artifacts and uses the
    strands_tools.swarm tool to dispatch specialist teams in parallel.

    Args:
        repo_path: Path to the repository.
        output_dir: Path to output directory with index artifacts.
        mode: Analysis mode ("standard", "full", "full+focus", etc.).
        hooks: Optional HookProviders for the coordinator.

    Returns:
        Configured Agent ready for invocation.
    """
    # Load index metadata
    from ..models.index import IndexMetadata

    metadata_path = output_dir / "index_metadata.json"
    if metadata_path.exists():
        metadata = _json.loads(metadata_path.read_text())
    else:
        logger.warning("No index_metadata.json found, coordinator will have limited context")
        metadata = IndexMetadata(
            file_count=0,
            languages={},
            frameworks=[],
            graph_stats={},
            top_entry_points=[],
            top_hotspots=[],
            has_signatures=False,
            has_orientation=False,
            indexed_at="",
        ).model_dump()

    # Pre-load graph into shared state
    graph_summary = "{}"
    graph_path = output_dir / "code_graph.json"
    if graph_path.exists():
        try:
            from ..tools.graph.model import CodeGraph
            from ..tools.graph.tools import _graphs

            data = graph_path.read_text()
            graph_data = _json.loads(data)
            code_graph = CodeGraph.from_node_link_data(graph_data)
            _graphs["main"] = code_graph
            graph_summary = _json.dumps(code_graph.describe(), indent=2)
            logger.info(
                f"Preloaded graph: {code_graph.node_count} nodes, {code_graph.edge_count} edges",
            )
        except (OSError, ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to preload graph: {e}")

    # Render system prompt
    system_prompt = _render_coordinator_prompt(
        repo_path=repo_path,
        output_dir=output_dir,
        metadata=metadata,
        graph_summary=graph_summary,
        mode=mode,
    )

    # Create model and tools
    model = _create_model()
    tools = _get_coordinator_tools()

    # Create the coordinator Agent
    agent = Agent(
        name="coordinator",
        system_prompt=system_prompt,
        model=model,
        tools=tools,
        structured_output_model=AnalysisResult,
        callback_handler=None,
    )

    # Apply hooks
    if hooks:
        for hook in hooks:
            agent.hooks.add_hook(hook)

    logger.info(
        f"Created coordinator agent with {len(tools)} tools, mode={mode}, repo={repo_path}",
    )

    return agent
