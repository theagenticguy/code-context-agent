"""FastMCP server exposing code-context-agent's core differentiators.

This server exposes capabilities that coding agents (Claude Code, Cursor, etc.)
cannot get from commodity MCP tools:

1. Full 10-phase analysis pipeline (start_analysis / check_analysis)
2. Code graph algorithms (query_code_graph)
3. Progressive graph exploration (explore_code_graph)
4. Analysis artifact access (resources)

Tools that already exist in the MCP marketplace (ripgrep search, LSP symbols,
git history, AST-grep) are intentionally NOT exposed here.

The analysis pipeline is exposed as a kickoff/poll pair to avoid MCP client
timeouts. Graph query and exploration tools operate on persisted artifacts
and return in sub-second time.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from fastmcp import FastMCP
from loguru import logger
from pydantic import Field

from ..config import DEFAULT_OUTPUT_DIR
from ..tools.graph.analysis import CodeAnalyzer
from ..tools.graph.disclosure import ProgressiveExplorer
from ..tools.graph.model import CodeGraph

if TYPE_CHECKING:
    from collections.abc import Callable

mcp = FastMCP(
    name="code-context-agent",
    instructions="""\
Automated codebase analysis and structural understanding server.

USE THIS SERVER WHEN YOU NEED TO:
- Understand an unfamiliar codebase's architecture and structure
- Find the most critical, high-traffic, or bottleneck code in a repository
- Discover how code is organized into logical modules and layers
- Identify tightly-coupled components and architectural risks
- Find entry points, foundational infrastructure, and business logic
- Get a narrated architecture overview for onboarding or code review
- Analyze code dependencies, coupling, and change impact

WHAT THIS SERVER PROVIDES (that other tools don't):
- Code graph analysis: PageRank, betweenness centrality, Louvain community
  detection, TrustRank, coupling measurement, dependency chain analysis
- Business logic discovery: ranked by graph importance scores
- Narrated CONTEXT.md: <=300-line architecture overview written by AI
- Compressed Tree-sitter signatures, curated source bundles

HOW TO USE:
1. If .code-context/ directory exists in the repo, skip to step 3 (already analyzed)
2. Run start_analysis(repo_path) then poll check_analysis(job_id) until done
3. Use query_code_graph to run algorithms (hotspots, modules, PageRank, etc.)
4. Use explore_code_graph for progressive drill-down starting with "overview"
5. Read artifacts via resources: analysis://<repo_path>/context, etc.

IMPORTANT: The analysis step (1-2) is a one-time batch job (5-20 min). The
graph query and exploration tools (3-4) are sub-second and are the primary
interactive surface. Check for .code-context/code_graph.json before running analysis.
""",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_dir(repo_path: str) -> Path:
    """Resolve the output directory for a repository."""
    return Path(repo_path).resolve() / DEFAULT_OUTPUT_DIR


def _load_graph(repo_path: str) -> CodeGraph:
    """Load a persisted code graph from .code-context/code_graph.json."""
    graph_path = _agent_dir(repo_path) / "code_graph.json"
    if not graph_path.exists():
        msg = f"No code graph at {graph_path}. Run start_analysis first."
        raise FileNotFoundError(msg)
    data = json.loads(graph_path.read_text())
    return CodeGraph.from_node_link_data(data)


def _read_artifact(repo_path: str, filename: str) -> str:
    """Read an analysis artifact from the .code-context directory."""
    path = _agent_dir(repo_path) / filename
    if not path.exists():
        msg = f"Artifact not found: {path}. Run start_analysis first."
        raise FileNotFoundError(msg)
    return path.read_text()


# ---------------------------------------------------------------------------
# Analysis job tracking (kickoff/poll pattern for long-running analysis)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict[str, Any]] = {}


async def _run_analysis_job(job_id: str, repo_path: str, focus: str | None, issue_context: str | None) -> None:
    """Background coroutine that runs the analysis and updates job state."""
    from ..agent.runner import run_analysis

    try:
        _jobs[job_id]["status"] = "running"
        result = await run_analysis(
            repo_path=repo_path,
            focus=focus,
            quiet=True,
            issue_context=issue_context,
        )
        _jobs[job_id]["status"] = result.get("status", "completed")
        _jobs[job_id]["result"] = result
    except Exception as e:  # noqa: BLE001
        logger.error(f"Analysis job {job_id} failed: {e}")
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool
async def start_analysis(
    repo_path: Annotated[
        str,
        Field(description="Absolute path to the repository root (e.g. '/Users/me/projects/myapp')"),
    ],
    focus: Annotated[
        str,
        Field(description="Optional focus area to prioritize (e.g. 'authentication', 'API layer', 'database')"),
    ] = "",
    issue: Annotated[
        str,
        Field(description="Optional GitHub issue reference (e.g. 'gh:1694', 'gh:owner/repo#1694')"),
    ] = "",
) -> dict:
    """Kick off full codebase analysis. Returns immediately with a job_id for polling.

    USE THIS WHEN: You need to analyze a codebase that hasn't been analyzed yet
    (no .code-context/ directory exists). This is a one-time batch operation.

    DO NOT USE IF: .code-context/code_graph.json already exists — go straight to
    query_code_graph or explore_code_graph instead.

    The analysis runs in the background (5-20 min) and produces:
    - .code-context/CONTEXT.md — narrated architecture overview
    - .code-context/code_graph.json — structural graph for algorithm queries
    - .code-context/CONTEXT.signatures.md — compressed Tree-sitter signatures
    - .code-context/CONTEXT.bundle.md — curated source code bundle
    - .code-context/analysis_result.json — structured analysis metadata

    NEXT STEP: Poll check_analysis(job_id) every 30 seconds until status
    is "completed", then use query_code_graph or explore_code_graph.

    Returns:
        {
            "job_id": "a1b2c3d4e5f6",
            "status": "starting",
            "repo_path": "/Users/me/projects/myapp",
            "output_dir": "/Users/me/projects/myapp/.code-context",
            "message": "Analysis started. Poll check_analysis(job_id) for progress."
        }
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        return {"error": f"Not a directory: {repo}"}

    # Resolve issue context before spawning the background task
    issue_context = None
    if issue:
        from ..issues import render_issue_context
        from ..issues.github import GitHubIssueProvider, parse_issue_ref

        try:
            provider_name, issue_ref = parse_issue_ref(issue)
            if provider_name == "gh":
                provider = GitHubIssueProvider()
                fetched_issue = provider.fetch(issue_ref)
                issue_context = render_issue_context(fetched_issue)
        except RuntimeError:
            pass  # proceed without issue context

    job_id = uuid.uuid4().hex[:12]
    output_dir = str(repo / DEFAULT_OUTPUT_DIR)
    _jobs[job_id] = {
        "status": "starting",
        "repo_path": str(repo),
        "output_dir": output_dir,
        "focus": focus or None,
        "result": None,
        "error": None,
    }

    # Store task reference to prevent GC and satisfy linter
    _jobs[job_id]["_task"] = asyncio.create_task(
        _run_analysis_job(job_id, str(repo), focus or None, issue_context),
    )

    logger.info(f"Analysis job {job_id} started for {repo}")
    return {
        "job_id": job_id,
        "status": "starting",
        "repo_path": str(repo),
        "output_dir": output_dir,
        "message": "Analysis started. Poll check_analysis(job_id) for progress.",
    }


@mcp.tool
def check_analysis(
    job_id: Annotated[str, Field(description="The job_id string returned by start_analysis (e.g. 'a1b2c3d4e5f6')")],
) -> dict:
    """Poll the status of a running analysis job. Call every 30 seconds until done.

    USE THIS AFTER: calling start_analysis. Keep polling until status is
    "completed" or "error".

    POLLING PATTERN:
    1. Call check_analysis(job_id)
    2. If status is "starting" or "running", wait 30 seconds, repeat
    3. If status is "completed", artifacts are ready — use query_code_graph
    4. If status is "error", check the error field
    5. If status is "stopped", partial artifacts may exist (hit time/turn limit)

    Returns (while running):
        {"job_id": "a1b2c3d4e5f6", "status": "running", "repo_path": "...", "output_dir": "..."}

    Returns (when complete):
        {
            "job_id": "a1b2c3d4e5f6",
            "status": "completed",
            "repo_path": "/Users/me/projects/myapp",
            "output_dir": "/Users/me/projects/myapp/.code-context",
            "result": {"status": "completed", "turn_count": 87, "duration_seconds": 542.3, ...},
            "artifacts": {
                "context": true, "graph": true, "manifest": true,
                "signatures": true, "bundle": true, "result": true
            }
        }
    """
    job = _jobs.get(job_id)
    if job is None:
        return {"error": f"Unknown job_id: {job_id}. Was start_analysis called in this server session?"}

    response: dict[str, Any] = {
        "job_id": job_id,
        "status": job["status"],
        "repo_path": job["repo_path"],
        "output_dir": job["output_dir"],
    }

    if job["status"] in ("completed", "stopped"):
        response["result"] = job["result"]
        # Check which artifacts were produced
        agent_dir = Path(job["output_dir"])
        response["artifacts"] = {
            name: (agent_dir / filename).exists()
            for name, filename in [
                ("context", "CONTEXT.md"),
                ("graph", "code_graph.json"),
                ("manifest", "files.all.txt"),
                ("signatures", "CONTEXT.signatures.md"),
                ("bundle", "CONTEXT.bundle.md"),
                ("result", "analysis_result.json"),
            ]
        }
    elif job["status"] == "error":
        response["error"] = job["error"]

    return response


# ---------------------------------------------------------------------------
# Graph algorithm dispatch helpers
# ---------------------------------------------------------------------------


def _build_algorithm_dispatch(
    analyzer: CodeAnalyzer,
    top_k: int,
    node_a: str,
    node_b: str,
    resolution: float,
    category: str,
) -> dict[str, Callable[[], dict[str, Any]]]:
    """Build dispatch table for graph algorithms."""
    return {
        "hotspots": lambda: {"algorithm": "hotspots", "results": analyzer.find_hotspots(top_k)},
        "foundations": lambda: {"algorithm": "foundations", "results": analyzer.find_foundations(top_k)},
        "trust": lambda: {"algorithm": "trust", "results": analyzer.find_trusted_foundations(top_k=top_k)},
        "modules": lambda: _run_modules(analyzer, resolution),
        "entry_points": lambda: {"algorithm": "entry_points", "results": analyzer.find_entry_points()},
        "coupling": lambda: _run_coupling(analyzer, node_a, node_b),
        "similar": lambda: _run_with_node(analyzer.get_similar_nodes, "similar", node_a, top_k),
        "dependencies": lambda: _run_dependencies(analyzer, node_a),
        "category": lambda: _run_category(analyzer, category),
        "triangles": lambda: {"algorithm": "triangles", "results": analyzer.find_triangles(top_k=top_k)},
    }


def _run_modules(analyzer: CodeAnalyzer, resolution: float) -> dict[str, Any]:
    results = analyzer.detect_modules(resolution)
    return {"algorithm": "modules", "module_count": len(results), "results": results}


def _run_coupling(analyzer: CodeAnalyzer, node_a: str, node_b: str) -> dict[str, Any]:
    if not node_a or not node_b:
        return {"error": "node_a and node_b required for coupling analysis"}
    return {"algorithm": "coupling", "results": analyzer.calculate_coupling(node_a, node_b)}


def _run_with_node(
    method: Callable,
    name: str,
    node_a: str,
    top_k: int,
) -> dict[str, Any]:
    if not node_a:
        return {"error": f"node_a required for {name} analysis"}
    return {"algorithm": name, "results": method(node_a, top_k)}


def _run_dependencies(analyzer: CodeAnalyzer, node_a: str) -> dict[str, Any]:
    if not node_a:
        return {"error": "node_a required for dependencies analysis"}
    return {"algorithm": "dependencies", "results": analyzer.get_dependency_chain(node_a, "outgoing")}


def _run_category(analyzer: CodeAnalyzer, category: str) -> dict[str, Any]:
    if not category:
        return {"error": "category required for category analysis"}
    return {"algorithm": "category", "category": category, "results": analyzer.find_clusters_by_category(category)}


@mcp.tool
def query_code_graph(
    repo_path: Annotated[
        str,
        Field(
            description="Absolute path to repo (must have .code-context/code_graph.json from prior analysis)",
        ),
    ],
    algorithm: Annotated[
        str,
        Field(
            description=(
                "Algorithm to run. One of: hotspots, foundations, trust, modules, "
                "entry_points, coupling, similar, dependencies, category, triangles"
            ),
        ),
    ],
    top_k: Annotated[
        int,
        Field(description="Max results for ranked analyses (default 10, use 20-30 for thorough review)"),
    ] = 10,
    node_a: Annotated[
        str,
        Field(
            description=(
                "Primary node ID for relationship queries. "
                "Format: 'filepath:symbol_name' (e.g. 'src/auth/service.py:AuthService')"
            ),
        ),
    ] = "",
    node_b: Annotated[
        str,
        Field(description="Second node ID for coupling analysis. Same format as node_a."),
    ] = "",
    resolution: Annotated[
        float,
        Field(
            description=(
                "Cluster granularity for 'modules' algorithm. "
                "<1.0 = fewer larger clusters, >1.0 = more smaller clusters"
            ),
        ),
    ] = 1.0,
    category: Annotated[
        str,
        Field(
            description=(
                "Business logic category for 'category' algorithm. "
                "Values: db, auth, http, validation, workflows, integrations"
            ),
        ),
    ] = "",
) -> dict:
    """Run graph algorithms on a pre-built code graph to find structural insights.

    USE THIS WHEN: You need to understand which code is most important,
    how code is organized, or how components relate to each other.

    PREREQUISITE: .code-context/code_graph.json must exist (from start_analysis or
    'code-context-agent analyze' CLI). Check for the file first.

    ALGORITHMS AND WHEN TO USE EACH:

    Finding important code:
    - "hotspots" — Betweenness centrality. Finds bottleneck/integration code that
      many paths go through. Use for: risk assessment, refactoring targets.
    - "foundations" — PageRank. Finds core infrastructure that important code
      depends on. Use for: understanding what's foundational, documentation priority.
    - "trust" — TrustRank (PageRank seeded from entry points). More noise-resistant
      than foundations. Use for: identifying truly important production code.
    - "entry_points" — Nodes with no incoming edges. Use for: finding where
      execution starts, understanding app structure.

    Finding structure:
    - "modules" — Louvain community detection. Groups densely connected code
      into logical clusters. Use for: architecture diagrams, understanding layers.

    Analyzing relationships (require node_a and/or node_b):
    - "coupling" — How tightly two nodes are connected. Use for: change impact,
      refactoring decisions. Requires node_a AND node_b.
    - "similar" — Personalized PageRank from a node. Finds related code.
      Use for: understanding a component's neighborhood. Requires node_a.
    - "dependencies" — BFS traversal from a node. Shows transitive dependencies.
      Use for: understanding what a component needs. Requires node_a.
    - "triangles" — Tightly-coupled triads. Use for: finding clusters of
      interdependent code that should be refactored together.

    Filtering:
    - "category" — All nodes in a business logic category (from AST-grep analysis).
      Use for: finding all database operations, auth logic, etc. Requires category.

    NODE ID FORMAT: Node IDs come from explore_code_graph or previous query results.
    Format is "filepath:symbol_name", e.g. "src/services/auth.py:AuthService" or
    "src/api/routes.ts:handleRequest".

    Returns example (for hotspots):
        {
            "algorithm": "hotspots",
            "results": [
                {"id": "src/core/engine.py:process", "name": "process",
                 "score": 0.85, "node_type": "function", "file_path": "src/core/engine.py"},
                ...
            ]
        }

    Returns example (for modules):
        {
            "algorithm": "modules",
            "module_count": 5,
            "results": [
                {"module_id": 0, "size": 15, "key_nodes": [...], "cohesion": 0.8},
                ...
            ]
        }
    """
    graph = _load_graph(repo_path)
    analyzer = CodeAnalyzer(graph)
    dispatch = _build_algorithm_dispatch(analyzer, top_k, node_a, node_b, resolution, category)
    handler = dispatch.get(algorithm)
    if handler is None:
        return {
            "error": (
                f"Unknown algorithm: {algorithm}. Valid: hotspots, foundations, trust, "
                "modules, entry_points, coupling, similar, dependencies, category, triangles"
            ),
        }
    return handler()


# ---------------------------------------------------------------------------
# Graph exploration dispatch helpers
# ---------------------------------------------------------------------------


def _build_explore_dispatch(
    explorer: ProgressiveExplorer,
    node_id: str,
    module_id: int,
    target_node: str,
    depth: int,
    category: str,
) -> dict[str, Callable[[], dict[str, Any]]]:
    """Build dispatch table for exploration actions."""
    return {
        "overview": lambda: {"action": "overview", **explorer.get_overview()},
        "expand_node": lambda: _explore_node(explorer, node_id, depth),
        "expand_module": lambda: _explore_module(explorer, module_id),
        "path": lambda: _explore_path(explorer, node_id, target_node),
        "category": lambda: _explore_category(explorer, category),
        "status": lambda: {"action": "status", **explorer.get_exploration_status()},
    }


def _explore_node(explorer: ProgressiveExplorer, node_id: str, depth: int) -> dict[str, Any]:
    if not node_id:
        return {"error": "node_id required for expand_node"}
    return {"action": "expand_node", **explorer.expand_node(node_id, depth)}


def _explore_module(explorer: ProgressiveExplorer, module_id: int) -> dict[str, Any]:
    if module_id < 0:
        return {"error": "module_id required for expand_module (integer from overview results)"}
    return {"action": "expand_module", **explorer.expand_module(module_id)}


def _explore_path(explorer: ProgressiveExplorer, node_id: str, target_node: str) -> dict[str, Any]:
    if not node_id or not target_node:
        return {"error": "node_id and target_node required for path"}
    return {"action": "path", **explorer.get_path_between(node_id, target_node)}


def _explore_category(explorer: ProgressiveExplorer, category: str) -> dict[str, Any]:
    if not category:
        return {"error": "category required for category exploration (e.g. 'db', 'auth', 'http')"}
    return {"action": "category", **explorer.explore_category(category)}


@mcp.tool
def explore_code_graph(
    repo_path: Annotated[
        str,
        Field(
            description="Absolute path to repo (must have .code-context/code_graph.json from prior analysis)",
        ),
    ],
    action: Annotated[
        str,
        Field(description="Exploration action. One of: overview, expand_node, expand_module, path, category, status"),
    ],
    node_id: Annotated[
        str,
        Field(
            description="Node ID for expand_node or path source. Format: 'filepath:symbol' (e.g. 'src/auth.py:login')",
        ),
    ] = "",
    module_id: Annotated[
        int,
        Field(description="Module ID (integer) for expand_module. Get from overview results modules[].module_id"),
    ] = -1,
    target_node: Annotated[
        str,
        Field(description="Target node ID for path finding. Same format as node_id."),
    ] = "",
    depth: Annotated[
        int,
        Field(
            description=(
                "BFS depth for expand_node. 1=direct neighbors (fast), 2=neighbors of neighbors, 3+=rarely needed"
            ),
        ),
    ] = 1,
    category: Annotated[
        str,
        Field(
            description=(
                "Business logic category for category exploration. Values: db, auth, http, validation, workflows"
            ),
        ),
    ] = "",
) -> dict:
    """Progressively explore a code graph, starting broad and drilling down.

    USE THIS WHEN: You want to understand a codebase step by step, starting
    with a high-level overview and drilling into specific areas of interest.

    PREREQUISITE: .code-context/code_graph.json must exist (from start_analysis or
    'code-context-agent analyze' CLI). Check for the file first.

    RECOMMENDED EXPLORATION FLOW:
    1. Start with action="overview" — returns entry points, hotspots, modules,
       and foundation code. This gives you node IDs and module IDs for drill-down.
    2. Pick interesting nodes from the overview results.
    3. Use action="expand_node" with a node_id to see its neighbors and relationships.
    4. Use action="expand_module" with a module_id to see a cluster's internals.
    5. Use action="path" with node_id + target_node to trace how two components connect.
    6. Use action="category" to see all code in a business logic category (db, auth, etc.).

    GETTING NODE IDs: Node IDs appear in results from overview (entry_points,
    hotspots, foundations), expand_node, and query_code_graph. They look like
    "src/services/auth.py:AuthService" or "src/api/handler.ts:processRequest".

    Returns example (for overview):
        {
            "action": "overview",
            "total_nodes": 342,
            "total_edges": 891,
            "entry_points": [{"id": "src/main.py:main", "name": "main", ...}],
            "hotspots": [{"id": "src/core/engine.py:process", "score": 0.85, ...}],
            "modules": [{"module_id": 0, "size": 45, "key_nodes": [...]}],
            "foundations": [{"id": "src/db/connection.py:get_pool", "score": 0.72, ...}],
            "explored_count": 25
        }

    Returns example (for expand_node):
        {
            "action": "expand_node",
            "center": "src/core/engine.py:process",
            "discovered_nodes": [{"id": "...", "name": "...", "edge_type": "calls"}],
            "edges": [...],
            "suggested_next": ["src/core/pipeline.py:Pipeline"],
            "explored_count": 40
        }
    """
    graph = _load_graph(repo_path)
    explorer = ProgressiveExplorer(graph)
    dispatch = _build_explore_dispatch(explorer, node_id, module_id, target_node, depth, category)
    handler = dispatch.get(action)
    if handler is None:
        return {
            "error": f"Unknown action: {action}. Valid: overview, expand_node, expand_module, path, category, status",
        }
    return handler()


@mcp.tool
def get_graph_stats(
    repo_path: Annotated[
        str,
        Field(
            description="Absolute path to repo (must have .code-context/code_graph.json from prior analysis)",
        ),
    ],
) -> dict:
    """Get summary statistics about a repository's code graph.

    USE THIS WHEN: You want a quick check of whether analysis was successful
    and what the graph contains before running algorithms.

    Returns node and edge counts broken down by type. A healthy graph from
    a medium codebase typically has 100-500 nodes and 200-2000 edges.

    Returns:
        {
            "node_count": 342,
            "edge_count": 891,
            "node_types": {"function": 180, "class": 45, "method": 90, "pattern_match": 27},
            "edge_types": {"calls": 400, "references": 250, "imports": 150, "tests": 91},
            "density": 0.0076
        }
    """
    graph = _load_graph(repo_path)
    return graph.describe()


# ---------------------------------------------------------------------------
# Resources — read-only access to analysis artifacts
# ---------------------------------------------------------------------------


@mcp.resource("analysis://{repo_path*}/context")
def read_context(repo_path: str) -> str:
    """Read the CONTEXT.md narrated architecture overview for a repository.

    This is the primary human-readable output of the analysis — a <=300 line
    markdown document covering architecture, business logic, key components,
    and risks. Best artifact to read first for codebase understanding.
    """
    return _read_artifact(f"/{repo_path}", "CONTEXT.md")


@mcp.resource("analysis://{repo_path*}/graph")
def read_graph(repo_path: str) -> str:
    """Read the raw code_graph.json (NetworkX node-link format).

    Contains all nodes (functions, classes, methods, pattern matches) and
    edges (calls, references, imports, inherits, tests, cochanges). This is
    the data that query_code_graph and explore_code_graph operate on.
    """
    return _read_artifact(f"/{repo_path}", "code_graph.json")


@mcp.resource("analysis://{repo_path*}/manifest")
def read_manifest(repo_path: str) -> str:
    """Read the files.all.txt complete file listing (one path per line).

    Every file in the repository, respecting .gitignore. Useful for
    understanding repository size and finding specific file paths.
    """
    return _read_artifact(f"/{repo_path}", "files.all.txt")


@mcp.resource("analysis://{repo_path*}/signatures")
def read_signatures(repo_path: str) -> str:
    """Read compressed Tree-sitter signatures (function/class signatures only, bodies stripped).

    Compact view of the codebase API surface. Useful for understanding
    the public interface of modules without reading full source code.
    """
    return _read_artifact(f"/{repo_path}", "CONTEXT.signatures.md")


@mcp.resource("analysis://{repo_path*}/bundle")
def read_bundle(repo_path: str) -> str:
    """Read the curated source code bundle (full source of key files).

    Contains the actual source code of the most important files identified
    during analysis. Larger than signatures but includes implementation details.
    """
    return _read_artifact(f"/{repo_path}", "CONTEXT.bundle.md")


@mcp.resource("analysis://{repo_path*}/result")
def read_result(repo_path: str) -> str:
    """Read the structured AnalysisResult JSON with ranked business logic and risks.

    Machine-readable analysis output containing: status, summary, ranked
    business_logic_items (with scores), architectural risks (with severity),
    generated file list, and graph statistics.
    """
    return _read_artifact(f"/{repo_path}", "analysis_result.json")
