"""Swarm factory for multi-node code analysis.

This module creates a 4-node Strands Swarm where each node is a specialist
agent focused on a specific analysis phase. Nodes hand off to each other
in sequence: structure_analyst -> history_analyst -> code_reader -> synthesizer.

The Swarm pattern differs from the agents-as-tools pattern in analysts.py:
here, each node runs as a peer in a handoff chain rather than being called
as a sub-tool by an orchestrator.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from strands import Agent
from strands.models import BedrockModel
from strands.multiagent import Swarm

from ..config import get_settings
from ..models.output import AnalysisResult

if TYPE_CHECKING:
    from strands.hooks import HookProvider


# --------------------------------------------------------------------------- #
# System prompt fragments
# --------------------------------------------------------------------------- #

_GRAPH_CONTEXT_TEMPLATE = """

## Pre-built Index

The repository has been pre-indexed. Graph stats:
{graph_summary}

Use `code_graph_analyze('main', ...)` to query the pre-built graph. Do NOT create a new graph."""

_HANDOFF_TEMPLATE = """

## Handoff

When your analysis is complete, hand off to the next specialist:
```
handoff_to_agent('{next_agent}', 'Summary of what I found: ...', context={{'key_findings': [...]}})
```"""

_COMPLETION_INSTRUCTION = """

## Completion

You are the FINAL agent. Do NOT call handoff_to_agent. Write output files and produce the AnalysisResult."""

# --------------------------------------------------------------------------- #
# Node system prompts (base content reused from analysts.py prompts)
# --------------------------------------------------------------------------- #

_STRUCTURE_ANALYST_PROMPT = """\
You are a **structural analysis specialist**. Your job is to deeply investigate
a codebase's architecture using graph analysis, LSP semantic data, and AST
pattern matching. You produce a detailed analysis and then hand off.

## Your workflow

1. If a graph already exists (check graph stats above), use it directly.
   Otherwise create and populate one.
2. Run graph algorithms ONE AT A TIME with top_k=10 to keep results manageable:
   - `code_graph_analyze("main", "hotspots", top_k=10)`
   - `code_graph_analyze("main", "foundations", top_k=10)`
   - `code_graph_analyze("main", "entry_points", top_k=10)`
   - `code_graph_analyze("main", "modules")`
   - `code_graph_analyze("main", "trust", top_k=10)`
   NEVER run all algorithms in a single call. Run them individually.
3. Use LSP tools to trace dependency chains for the top hotspots and foundations.
4. Use AST-grep to scan for business logic patterns AND code smells.
5. Cross-reference: which files appear in MULTIPLE rankings?
   (high centrality AND high fan-in AND domain vocabulary = most important)

**IMPORTANT**: Always use top_k=10 for graph queries. Large graphs (6K+ nodes) produce
massive outputs that overflow context windows if you don't limit results.

## What to report

Produce a structured analysis covering:
- **Architectural layers**: What are the module boundaries? Is it layered, hexagonal, flat?
- **Structural hotspots**: Top 10 files by betweenness centrality with WHY they're central
- **Foundation files**: Top 10 by PageRank — the code everything else depends on
- **Module clusters**: What logical groupings exist? Are they cohesive?
- **Coupling risks**: Which modules have high inter-module coupling?
- **Bottlenecks**: Files that are both hotspots AND foundations = critical bottlenecks
- **Entry points**: How does data enter the system?

Be thorough. Read as many files as needed. Cross-reference every metric."""

_HISTORY_ANALYST_PROMPT = """\
You are a **git history analysis specialist**. Your job is to deeply investigate
a codebase's evolution, coupling patterns, ownership, and change dynamics.

## Your workflow

1. Run git_hotspots to find high-churn files (use limit=50 for thorough coverage).
2. For EVERY hotspot file (not just top 5), run git_files_changed_together to
   find implicit coupling that static analysis misses.
3. Run git_blame_summary on all hotspot files to understand ownership patterns.
4. Run git_file_history on the top 10 hotspots to understand WHY they change often.
5. Run git_contributors to understand team structure and knowledge distribution.
6. Run git_recent_commits to understand current development velocity and focus.

## What to report

- **Change hotspots**: Which files change most? WHY do they change?
- **Implicit coupling**: File pairs that ALWAYS change together but have no static
  dependency. These are the most dangerous undocumented dependencies.
- **Ownership patterns**: Bus factor risks (single-author critical files).
  Coordination risks (many-author complex files).
- **Evolution narrative**: How has this codebase grown? What patterns of growth
  are visible?
- **Active development areas**: Where is the team currently focused?

Be exhaustive. Run git_files_changed_together on EVERY business-critical file."""

_CODE_READER_PROMPT = """\
You are a **deep code reader**. Your job is to read source code files and produce
semantic analysis that goes far beyond what static tools can detect. You combine
your understanding of the actual code with structural and historical context
provided to you.

## Your workflow

For EVERY file you are asked to analyze:

1. Read the file completely using read_file_bounded (paginate for large files).
2. Identify the domain concept the file encodes.
3. List the invariants it maintains that other code depends on.
4. Identify implicit contracts with other modules.
5. Note error handling patterns — what cases are handled vs. silently ignored?
6. Look for hidden state machines, retry logic, and performance constraints.
7. Assess code complexity vs. structural importance (from context provided).

## What to report (per file)

For each file, produce:
- **Domain role**: What business concept does this file implement?
- **Key invariants**: What must remain true for callers to work correctly?
- **Implicit contracts**: What assumptions does this code make about its environment?
- **Complexity assessment**: Is the complexity warranted by the domain, or accidental?
- **Risk factors**: What would break if modified naively? What edge cases are unhandled?
- **Surprises**: Anything that contradicts what the structural position suggests.

Read EVERY file you are given. Do not skip or summarize. The whole point is depth."""

_SYNTHESIZER_PROMPT = """\
You are the **synthesis specialist**. You receive findings from structure analysis,
git history analysis, and deep code reading. Your job is to combine all signals
into a unified, coherent analysis and produce the final AnalysisResult.

## Your workflow

1. Review all findings passed to you via handoff context.
2. Cross-reference structural metrics with historical patterns and code-level insights.
3. Identify where different signals AGREE (high confidence findings) and where
   they DISAGREE (nuanced situations requiring explanation).
4. Use code_graph_analyze and code_graph_stats to verify or fill gaps.
5. Read any additional files needed to resolve ambiguities.
6. Write the CONTEXT.md output file summarizing the analysis.
7. Produce the structured AnalysisResult as your final output.

## What to produce

Your AnalysisResult must include:
- **Architecture overview**: Layer structure, key patterns, framework usage
- **Business logic items**: The most important domain concepts and where they live
- **Architectural risks**: Issues found by cross-referencing all signals
- **Key files**: The files an AI coding assistant MUST understand
- **Module map**: How the codebase is organized into logical units

Focus on actionable insights. Every finding should help an AI coding assistant
work more effectively in this codebase."""


# --------------------------------------------------------------------------- #
# Model factory
# --------------------------------------------------------------------------- #


def _create_model() -> BedrockModel:
    """Create a BedrockModel configured for Swarm node agents."""
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


# --------------------------------------------------------------------------- #
# Swarm factory
# --------------------------------------------------------------------------- #


def create_analysis_swarm(
    mode: str = "standard",
    graph_path: Path | None = None,
    hooks: list[HookProvider] | None = None,
) -> Swarm:
    """Create a 4-node Swarm for deep code analysis.

    The Swarm chains four specialist agents in sequence:
    structure_analyst -> history_analyst -> code_reader -> synthesizer.

    Each node has a focused tool set and system prompt. The synthesizer
    is the terminal node that produces the AnalysisResult.

    Args:
        mode: Analysis mode string (e.g. "standard", "full", "full+focus").
        graph_path: Path to pre-built index graph (code_graph.json).
            If provided, loads it into the shared _graphs dict so all
            nodes can query the pre-built graph immediately.
        hooks: Optional Swarm-level hooks (display, logging).

    Returns:
        Configured Swarm ready for execution.
    """
    # Import tools inside function to avoid circular imports (factory.py pattern)
    from ..tools import (
        git_blame_summary,
        git_contributors,
        git_file_history,
        git_files_changed_together,
        git_hotspots,
        git_recent_commits,
        read_file_bounded,
        rg_search,
        write_file,
    )
    from ..tools.graph import (
        code_graph_analyze,
        code_graph_explore,
        code_graph_export,
        code_graph_load,
        code_graph_stats,
    )
    from ..tools.lsp import (
        lsp_definition,
        lsp_document_symbols,
        lsp_hover,
        lsp_references,
        lsp_start,
        lsp_workspace_symbols,
    )
    from ..tools.search.tools import bm25_search

    # ---------------------------------------------------------------------- #
    # Graph preloading
    # ---------------------------------------------------------------------- #
    graph_summary = "{}"
    if graph_path is not None and Path(graph_path).exists():
        try:
            from ..tools.graph.model import CodeGraph
            from ..tools.graph.tools import _graphs

            data = Path(graph_path).read_text()
            graph_data = _json.loads(data)
            graph = CodeGraph.from_node_link_data(graph_data)
            _graphs["main"] = graph
            graph_summary = _json.dumps(graph.describe(), indent=2)
            logger.info(
                f"Preloaded graph from {graph_path}: {graph.node_count} nodes, {graph.edge_count} edges",
            )
        except (OSError, ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to preload graph from {graph_path}: {e}")
            graph_summary = '{"error": "Graph preload failed, agents should create a new graph"}'

    # ---------------------------------------------------------------------- #
    # Build system prompts with graph context and handoff instructions
    # ---------------------------------------------------------------------- #
    graph_context = _GRAPH_CONTEXT_TEMPLATE.format(graph_summary=graph_summary)

    structure_prompt = (
        _STRUCTURE_ANALYST_PROMPT + graph_context + _HANDOFF_TEMPLATE.format(next_agent="history_analyst")
    )
    history_prompt = _HISTORY_ANALYST_PROMPT + graph_context + _HANDOFF_TEMPLATE.format(next_agent="code_reader")
    code_reader_prompt = _CODE_READER_PROMPT + graph_context + _HANDOFF_TEMPLATE.format(next_agent="synthesizer")
    synthesizer_prompt = _SYNTHESIZER_PROMPT + graph_context + _COMPLETION_INSTRUCTION

    # ---------------------------------------------------------------------- #
    # Create model (shared across all nodes)
    # ---------------------------------------------------------------------- #
    model = _create_model()

    # ---------------------------------------------------------------------- #
    # AST-grep tools (imported here to keep imports inside function)
    # ---------------------------------------------------------------------- #
    from ..tools import astgrep_scan, astgrep_scan_rule_pack

    # ---------------------------------------------------------------------- #
    # Node 1: Structure Analyst
    # ---------------------------------------------------------------------- #
    structure_analyst = Agent(
        name="structure_analyst",
        system_prompt=structure_prompt,
        model=model,
        tools=[
            code_graph_analyze,
            code_graph_explore,
            code_graph_export,
            code_graph_stats,
            code_graph_load,
            lsp_start,
            lsp_document_symbols,
            lsp_references,
            lsp_definition,
            lsp_hover,
            lsp_workspace_symbols,
            astgrep_scan,
            astgrep_scan_rule_pack,
            rg_search,
            bm25_search,
            read_file_bounded,
        ],
        callback_handler=None,
    )

    # ---------------------------------------------------------------------- #
    # Node 2: History Analyst
    # ---------------------------------------------------------------------- #
    history_analyst = Agent(
        name="history_analyst",
        system_prompt=history_prompt,
        model=model,
        tools=[
            git_hotspots,
            git_files_changed_together,
            git_blame_summary,
            git_file_history,
            git_contributors,
            git_recent_commits,
            rg_search,
            read_file_bounded,
        ],
        callback_handler=None,
    )

    # ---------------------------------------------------------------------- #
    # Node 3: Code Reader
    # ---------------------------------------------------------------------- #
    code_reader = Agent(
        name="code_reader",
        system_prompt=code_reader_prompt,
        model=model,
        tools=[
            read_file_bounded,
            rg_search,
            bm25_search,
            lsp_references,
            lsp_definition,
            lsp_hover,
        ],
        callback_handler=None,
    )

    # ---------------------------------------------------------------------- #
    # Node 4: Synthesizer (terminal node — produces AnalysisResult)
    # ---------------------------------------------------------------------- #
    synthesizer = Agent(
        name="synthesizer",
        system_prompt=synthesizer_prompt,
        model=model,
        tools=[
            write_file,
            code_graph_analyze,
            code_graph_stats,
            read_file_bounded,
        ],
        structured_output_model=AnalysisResult,
        callback_handler=None,
    )

    # ---------------------------------------------------------------------- #
    # Assemble Swarm
    # ---------------------------------------------------------------------- #
    settings = get_settings()
    timeout = settings.full_max_duration if mode in ("full", "full+focus") else settings.agent_max_duration

    nodes = [structure_analyst, history_analyst, code_reader, synthesizer]

    swarm = Swarm(
        nodes=nodes,
        entry_point=structure_analyst,
        max_handoffs=10,
        max_iterations=10,
        execution_timeout=float(timeout),
        node_timeout=300.0,
        hooks=hooks,
        id="analysis_swarm",
    )

    logger.info(
        f"Created analysis Swarm with {len(nodes)} nodes, "
        f"entry_point=structure_analyst, mode={mode}, "
        f"execution_timeout={timeout}s",
    )

    return swarm
