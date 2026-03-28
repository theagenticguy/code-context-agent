"""Specialist sub-agents for deep analysis phases.

These agents are passed as tools to the main orchestrator agent.
When the orchestrator calls them, each runs its own full agentic loop
with focused tools and system prompt, producing a detailed analysis
report that feeds back into the orchestrator's synthesis.

The Agents-as-Tools pattern from Strands: each sub-agent variable name
becomes the tool name the orchestrator sees.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from strands import Agent
from strands.models import BedrockModel

from ..config import get_settings

# --------------------------------------------------------------------------- #
# System prompts for specialist agents
# --------------------------------------------------------------------------- #

_STRUCTURE_ANALYST_PROMPT = """\
You are a **structural analysis specialist**. Your job is to deeply investigate
a codebase's architecture using graph analysis, LSP semantic data, and AST
pattern matching. You do NOT write output files — you produce a detailed
analysis report as your response.

## Your workflow

1. If a graph already exists, load it. Otherwise create and populate one.
2. Run ALL relevant graph algorithms: hotspots, foundations, trust, modules,
   coupling, entry_points, triangles, similar, dependencies.
3. Use LSP tools to trace dependency chains for the top hotspots and foundations.
4. Use AST-grep to scan for business logic patterns AND code smells.
5. Cross-reference: which files appear in MULTIPLE rankings?
   (high centrality AND high fan-in AND domain vocabulary = most important)

## What to report

Produce a structured analysis covering:
- **Architectural layers**: What are the module boundaries? Is it layered, hexagonal, flat?
- **Structural hotspots**: Top 10 files by betweenness centrality with WHY they're central
- **Foundation files**: Top 10 by PageRank — the code everything else depends on
- **Module clusters**: What logical groupings exist? Are they cohesive?
- **Coupling risks**: Which modules have high inter-module coupling?
- **Bottlenecks**: Files that are both hotspots AND foundations = critical bottlenecks
- **Entry points**: How does data enter the system?

Be thorough. Read as many files as needed. Cross-reference every metric.
If you include any diagrams, use mermaid code fences — never ASCII art.
"""

_HISTORY_ANALYST_PROMPT = """\
You are a **git history analysis specialist**. Your job is to deeply investigate
a codebase's evolution, coupling patterns, ownership, and change dynamics.
You do NOT write output files — you produce a detailed analysis report.

## Your workflow

1. Run git_hotspots to find high-churn files (use limit=50 for thorough coverage).
2. For EVERY hotspot file (not just top 5), run git_files_changed_together to
   find implicit coupling that static analysis misses.
3. Run git_blame_summary on all hotspot files to understand ownership patterns.
4. Run git_file_history on the top 10 hotspots to understand WHY they change often.
5. Run git_contributors to understand team structure and knowledge distribution.
6. Run git_recent_commits to understand current development velocity and focus.

## What to report

- **Change hotspots**: Which files change most? WHY do they change? (config thrash
  vs. genuine complexity vs. bug magnets)
- **Implicit coupling**: File pairs that ALWAYS change together but have no static
  dependency. These are the most dangerous undocumented dependencies.
- **Ownership patterns**: Bus factor risks (single-author critical files).
  Coordination risks (many-author complex files).
- **Evolution narrative**: How has this codebase grown? What patterns of growth
  are visible? (organic accretion vs. planned refactoring vs. feature branches)
- **Active development areas**: Where is the team currently focused?

Be exhaustive. Run git_files_changed_together on EVERY business-critical file,
not just the top few. The implicit coupling map is the most valuable output.
If you include any diagrams, use mermaid code fences — never ASCII art.
"""

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

## Cross-referencing

You will receive structural context (graph metrics, git data) along with the file
list. USE IT. Before reading each file, check what the metrics predict about it.
After reading, note where the code confirms or contradicts the metrics.

Read EVERY file you are given. Do not skip or summarize. The whole point is depth.
If you include any diagrams, use mermaid code fences — never ASCII art.
"""


def _create_model() -> BedrockModel:
    """Create a BedrockModel configured for deep analysis sub-agents."""
    settings = get_settings()
    return BedrockModel(
        model_id=settings.model_id,
        region_name=settings.region,
        temperature=settings.temperature,
        additional_request_fields={
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": settings.full_reasoning_effort},
            "anthropic_beta": ["context-1m-2025-08-07"],
        },
    )


def create_analyst_agents() -> list[Any]:
    """Create specialist sub-agents for deep analysis.

    Returns Agent instances that the orchestrator uses as tools.
    The variable names become the tool names visible to the model.

    Returns:
        List of Agent instances configured as specialist analysts.
    """
    # Import tools inside function to match factory.py pattern (avoid circular imports)
    from ..tools import (
        git_blame_summary,
        git_contributors,
        git_file_history,
        git_files_changed_together,
        git_hotspots,
        git_recent_commits,
        read_file_bounded,
        rg_search,
    )
    from ..tools.graph import (
        code_graph_analyze,
        code_graph_create,
        code_graph_explore,
        code_graph_export,
        code_graph_ingest_astgrep,
        code_graph_ingest_git,
        code_graph_ingest_lsp,
        code_graph_load,
        code_graph_save,
        code_graph_stats,
    )
    from ..tools.graph.tools import (
        code_graph_ingest_clones,
        code_graph_ingest_inheritance,
        code_graph_ingest_rg,
        code_graph_ingest_tests,
    )
    from ..tools.lsp import (
        lsp_definition,
        lsp_document_symbols,
        lsp_hover,
        lsp_references,
        lsp_workspace_symbols,
    )
    from ..tools.search.tools import bm25_search

    model = _create_model()

    # --- Structure Analyst: graph + LSP + AST tools ---
    from ..tools import astgrep_scan, astgrep_scan_rule_pack

    analyze_structure = Agent(
        system_prompt=_STRUCTURE_ANALYST_PROMPT,
        model=model,
        tools=[
            code_graph_create,
            code_graph_load,
            code_graph_save,
            code_graph_ingest_lsp,
            code_graph_ingest_astgrep,
            code_graph_ingest_rg,
            code_graph_ingest_inheritance,
            code_graph_ingest_tests,
            code_graph_ingest_git,
            code_graph_ingest_clones,
            code_graph_analyze,
            code_graph_explore,
            code_graph_export,
            code_graph_stats,
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

    # --- History Analyst: git tools ---
    analyze_history = Agent(
        system_prompt=_HISTORY_ANALYST_PROMPT,
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

    # --- Code Reader: read + search tools ---
    analyze_code = Agent(
        system_prompt=_CODE_READER_PROMPT,
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

    logger.info("Created 3 specialist sub-agents: analyze_structure, analyze_history, analyze_code")
    return [analyze_structure, analyze_history, analyze_code]
