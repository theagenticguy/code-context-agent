"""FastMCP server exposing code-context-agent's core differentiators.

This server complements GitNexus (structural code intelligence) with:

1. Full analysis pipeline (start_analysis / check_analysis) — multi-agent
   narrative generation producing CONTEXT.md and BUNDLE.{area}.md files
2. Git evolution analysis (hotspots, coupling, contributors) — GitNexus
   doesn't track commit-level churn and co-change patterns
3. Static analysis findings (semgrep, typecheck, lint, complexity, dead code)
4. Analysis artifact access (resources)

Tools that GitNexus already provides (structural search, symbol context,
blast radius, execution flows, community detection, Cypher queries) are
intentionally NOT duplicated here.

The analysis pipeline is exposed as a kickoff/poll pair to avoid MCP client
timeouts.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastmcp import FastMCP
from loguru import logger
from pydantic import Field

from ..config import DEFAULT_OUTPUT_DIR

mcp = FastMCP(
    name="code-context-agent",
    instructions="""\
Automated codebase analysis and narrative documentation server.

USE THIS SERVER WHEN YOU NEED TO:
- Run a full multi-agent analysis to produce narrated architecture documentation
- Access git evolution data (hotspot rankings, co-change coupling, contributors)
- Read static analysis findings (semgrep, typecheck, lint, complexity, dead code)
- Get a compact heuristic summary of a codebase's key metrics

WHAT THIS SERVER PROVIDES (that GitNexus doesn't):
- Multi-agent narrative analysis: CONTEXT.md + BUNDLE.{area}.md files
- Git evolution: hotspot rankings, co-change coupling, bus factor risks
- Static scanner results: semgrep, OWASP, type errors, lint, complexity, dead code
- Compressed Tree-sitter signatures, curated source bundles

WHAT TO USE GitNexus FOR INSTEAD:
- Structural code search → gitnexus query
- Symbol context (callers/callees) → gitnexus context
- Blast radius / impact analysis → gitnexus impact
- Execution flow tracing → gitnexus processes
- Community/cluster detection → gitnexus clusters
- Custom graph queries → gitnexus cypher

HOW TO USE:
1. If .code-context/ directory exists, skip to step 3 (already analyzed)
2. Run start_analysis(repo_path) then poll check_analysis(job_id) until done
3. Use git_evolution for churn/coupling data GitNexus doesn't track
4. Use static_scan_findings for security/quality scan results
5. Read artifacts via resources: analysis://<repo_path>/context, etc.

IMPORTANT: The analysis step (1-2) is a batch job (5-20 min). Other tools
are sub-second lookups against persisted index artifacts.
""",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_hints(result: dict[str, Any], hints: list[str]) -> dict[str, Any]:
    """Append next-step hints to an MCP tool response (returns a new dict)."""
    return {**result, "next_steps": hints}


def _agent_dir(repo_path: str) -> Path:
    """Resolve the output directory for a repository."""
    return Path(repo_path).resolve() / DEFAULT_OUTPUT_DIR


def _read_artifact(repo_path: str, filename: str) -> str:
    """Read an analysis artifact from the .code-context directory."""
    path = _agent_dir(repo_path) / filename
    if not path.exists():
        msg = f"Artifact not found: {path}. Run start_analysis first."
        raise FileNotFoundError(msg)
    return path.read_text()


def _load_json_artifact(path: Path) -> Any | None:
    """Load a JSON artifact, returning None on missing or parse error."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


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

        # Auto-register in the multi-repo registry
        from code_context_agent.mcp.registry import Registry

        registry = Registry()
        alias = Path(repo_path).name
        registry.register(alias, repo_path)
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

    USE THIS WHEN: You need to produce narrated architecture documentation
    (CONTEXT.md, BUNDLE.{area}.md) for a codebase. This dispatches multiple
    AI agent teams to investigate the code and synthesize findings.

    DO NOT USE IF: You just need structural code intelligence (search, symbol
    context, blast radius) — use GitNexus tools directly instead.

    The analysis runs in the background (5-20 min) and produces:
    - .code-context/CONTEXT.md — narrated architecture overview
    - .code-context/bundles/BUNDLE.{area}.md — deep-dive area narratives
    - .code-context/CONTEXT.signatures.md — compressed Tree-sitter signatures
    - .code-context/analysis_result.json — structured analysis metadata
    - .code-context/heuristic_summary.json — compact index metrics

    NEXT STEP: Poll check_analysis(job_id) every 30 seconds until status
    is "completed", then read the artifacts.

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
    return _add_hints(
        {
            "job_id": job_id,
            "status": "starting",
            "repo_path": str(repo),
            "output_dir": output_dir,
            "message": "Analysis started. Poll check_analysis(job_id) for progress.",
        },
        [
            f"Poll with check_analysis(job_id='{job_id}') every 30 seconds until completed",
            "While waiting, use GitNexus tools for immediate structural queries",
        ],
    )


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
    3. If status is "completed", artifacts are ready
    4. If status is "error", check the error field
    5. If status is "stopped", partial artifacts may exist (hit time/turn limit)

    Returns (when complete):
        {
            "job_id": "a1b2c3d4e5f6",
            "status": "completed",
            "repo_path": "/Users/me/projects/myapp",
            "output_dir": "/Users/me/projects/myapp/.code-context",
            "result": {"status": "completed", "turn_count": 87, "duration_seconds": 542.3, ...},
            "artifacts": {
                "context": true, "manifest": true,
                "signatures": true, "result": true
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
                ("manifest", "files.all.txt"),
                ("signatures", "CONTEXT.signatures.md"),
                ("result", "analysis_result.json"),
                ("heuristic_summary", "heuristic_summary.json"),
            ]
        }
    elif job["status"] == "error":
        response["error"] = job["error"]

    # Context-sensitive hints based on job status
    status = job["status"]
    if status in ("running", "starting"):
        hints = [f"Continue polling check_analysis(job_id='{job_id}') — analysis is still in progress"]
    elif status == "completed":
        hints = [
            f"Read analysis://{job['repo_path']}/context for the narrative architecture document",
            "Use git_evolution(repo_path, analysis='hotspots') for churn data",
            "Use static_scan_findings(repo_path) for security/quality findings",
        ]
    elif status == "error":
        hints = [
            "Check the error message for details",
            "Retry with start_analysis if the error is transient",
        ]
    elif status == "stopped":
        hints = ["Analysis was interrupted — review partial results if artifacts exist"]
    else:
        hints = [f"Continue polling check_analysis(job_id='{job_id}')"]

    return _add_hints(response, hints)


@mcp.tool
def list_repos() -> dict:
    """List all repositories registered in the code-context-agent registry.

    USE THIS WHEN: You want to discover which repositories have been analyzed
    and are available for querying.

    Returns:
        {"repos": [{"alias": "...", "path": "...", "analyzed_at": "...", ...}], "count": 3}
    """
    from code_context_agent.mcp.registry import Registry

    registry = Registry()
    repos = registry.list_repos()
    return _add_hints(
        {"repos": repos, "count": len(repos)},
        [
            "Run start_analysis(repo_path=<path>) to analyze a new repo",
            "Use GitNexus tools for structural queries on indexed repos",
        ],
    )


@mcp.tool
def git_evolution(  # noqa: C901, PLR0911
    repo_path: Annotated[
        str,
        Field(description="Absolute path to repo (must have .code-context/ from prior index or analysis)"),
    ],
    analysis: Annotated[
        str,
        Field(
            description=(
                "Type of git evolution analysis. One of: "
                "'hotspots' (files ranked by commit frequency), "
                "'coupling' (files that change together), "
                "'contributors' (contributor breakdown per directory), "
                "'summary' (all git metrics from heuristic summary)"
            ),
        ),
    ] = "summary",
) -> dict:
    """Query git evolution data that GitNexus doesn't track.

    USE THIS WHEN: You need commit-level churn patterns, co-change coupling,
    bus factor risks, or contributor breakdown. These signals complement
    GitNexus's structural analysis with temporal/social dimensions.

    DO NOT USE IF: You need structural relationships (calls, imports,
    inheritance) — use GitNexus context/impact/query tools instead.

    PREREQUISITE: .code-context/ must exist from a prior index or analysis run.

    Returns vary by analysis type:
    - hotspots: {"hotspots": [{"path": "...", "commits": 42, "percentage": 21.0}]}
    - coupling: {"coupled_pairs": [{"a": "...", "b": "...", "coupling": 0.85}]}
    - contributors: {"contributors": N, "bus_factor_risks": [...]}
    - summary: {"total_commits": N, "contributors": N, "coupled_pairs": [...], ...}
    """
    agent_dir = _agent_dir(repo_path)

    if analysis == "summary":
        heuristic = _load_json_artifact(agent_dir / "heuristic_summary.json")
        if heuristic and "git" in heuristic:
            return _add_hints(
                {"analysis": "summary", **heuristic["git"]},
                [
                    "Use git_evolution(analysis='hotspots') for detailed file churn ranking",
                    "Use git_evolution(analysis='coupling') for co-change pairs",
                ],
            )
        return {"error": "No git data in heuristic summary. Run start_analysis or index first."}

    if analysis == "hotspots":
        data = _load_json_artifact(agent_dir / "git_hotspots.json")
        if data:
            return _add_hints(
                {"analysis": "hotspots", **data},
                ["Cross-reference top hotspots with GitNexus impact analysis for blast radius"],
            )
        # Fallback to heuristic summary
        heuristic = _load_json_artifact(agent_dir / "heuristic_summary.json")
        if heuristic and "git" in heuristic:
            return _add_hints(
                {"analysis": "hotspots", "source": "heuristic_summary", **heuristic.get("git", {})},
                ["Full hotspot data not available; showing summary from heuristic_summary.json"],
            )
        return {"error": "No hotspot data found. Run start_analysis or index first."}

    if analysis == "coupling":
        data = _load_json_artifact(agent_dir / "git_cochanges.json")
        if data:
            return _add_hints(
                {"analysis": "coupling", **data},
                ["High coupling (>70%) suggests files should be refactored together"],
            )
        heuristic = _load_json_artifact(agent_dir / "heuristic_summary.json")
        if heuristic and "git" in heuristic:
            return _add_hints(
                {
                    "analysis": "coupling",
                    "source": "heuristic_summary",
                    "most_coupled_pairs": heuristic.get("git", {}).get("most_coupled_pairs", []),
                },
                ["Full coupling data not available; showing top pairs from heuristic_summary.json"],
            )
        return {"error": "No coupling data found. Run start_analysis or index first."}

    if analysis == "contributors":
        heuristic = _load_json_artifact(agent_dir / "heuristic_summary.json")
        if heuristic:
            git_data = heuristic.get("git", {})
            complexity_data = heuristic.get("complexity", {})
            return _add_hints(
                {
                    "analysis": "contributors",
                    "active_contributors": git_data.get("active_contributors", 0),
                    "total_commits": git_data.get("total_commits_analyzed", 0),
                    "bus_factor_risks": complexity_data.get("bus_factor_risks", []),
                },
                ["Bus factor risks indicate directories with a single contributor"],
            )
        return {"error": "No contributor data found. Run start_analysis or index first."}

    return {"error": f"Unknown analysis type: {analysis}. Valid: hotspots, coupling, contributors, summary"}


@mcp.tool
def static_scan_findings(
    repo_path: Annotated[
        str,
        Field(description="Absolute path to repo (must have .code-context/ from prior index or analysis)"),
    ],
    scanner: Annotated[
        str,
        Field(
            description=(
                "Which scanner results to read. One of: "
                "'all' (summary of all scanners), "
                "'semgrep' (security findings by severity), "
                "'typecheck' (type errors from ty/pyright), "
                "'lint' (ruff violations), "
                "'complexity' (cyclomatic complexity from radon), "
                "'dead_code' (unused code from vulture/knip)"
            ),
        ),
    ] = "all",
) -> dict:
    """Read static analysis findings from the deterministic index.

    USE THIS WHEN: You need security findings, type errors, lint violations,
    complexity metrics, or dead code reports. These come from tools like
    semgrep, ty/pyright, ruff, radon, and vulture — run during indexing.

    DO NOT USE IF: You need structural code relationships — use GitNexus.

    PREREQUISITE: .code-context/ must exist from a prior index or analysis run.

    Returns vary by scanner:
    - all: {"health": {"semgrep_findings": {...}, "type_errors": N, "lint_violations": N, ...}}
    - semgrep: {"findings": [...], "severity_counts": {"critical": N, "high": N, ...}}
    - typecheck: {"errors": [...], "count": N}
    - lint: {"violations": [...], "count": N}
    - complexity: {"functions": [...], "avg_complexity": N}
    - dead_code: {"symbols": [...], "count": N}
    """
    agent_dir = _agent_dir(repo_path)

    if scanner == "all":
        heuristic = _load_json_artifact(agent_dir / "heuristic_summary.json")
        if heuristic and "health" in heuristic:
            return _add_hints(
                {"scanner": "all", **heuristic["health"]},
                [
                    "Use static_scan_findings(scanner='semgrep') for detailed security findings",
                    "Use static_scan_findings(scanner='complexity') for function-level complexity",
                ],
            )
        return {"error": "No health data in heuristic summary. Run start_analysis or index first."}

    # Direct artifact reads for specific scanners
    artifact_map = {
        "semgrep": "semgrep_auto.json",
        "typecheck": "typecheck.json",
        "lint": "lint.json",
        "complexity": "complexity.json",
        "dead_code": "dead_code_py.json",
    }

    filename = artifact_map.get(scanner)
    if filename is None:
        return {"error": f"Unknown scanner: {scanner}. Valid: all, semgrep, typecheck, lint, complexity, dead_code"}

    data = _load_json_artifact(agent_dir / filename)
    if data is None:
        return {"error": f"No {scanner} data at {agent_dir / filename}. Was the scanner available during indexing?"}

    return _add_hints(
        {"scanner": scanner, "data": data},
        [f"Cross-reference {scanner} findings with GitNexus impact analysis for affected code paths"],
    )


@mcp.tool
def heuristic_summary(
    repo_path: Annotated[
        str,
        Field(description="Absolute path to repo (must have .code-context/ from prior index or analysis)"),
    ],
) -> dict:
    """Read the compact heuristic summary produced by the deterministic indexer.

    USE THIS WHEN: You want a quick overview of a codebase's key metrics
    before deciding whether to run a full analysis or which areas to focus on.

    The heuristic summary is the bridge between cheap deterministic indexing
    and expensive multi-agent analysis. It tells you:
    - Volume: file count, lines, tokens, languages
    - Health: semgrep findings, type errors, lint violations, complexity, dead code
    - Git: commit count, contributor count, most coupled file pairs
    - GitNexus: whether the repo has been indexed by GitNexus

    Returns:
        The full heuristic_summary.json content.
    """
    agent_dir = _agent_dir(repo_path)
    data = _load_json_artifact(agent_dir / "heuristic_summary.json")
    if data is None:
        return {"error": "No heuristic summary found. Run start_analysis or index first."}

    return _add_hints(
        data,
        [
            "Use start_analysis for full multi-agent narrative documentation",
            "Use git_evolution for detailed churn/coupling analysis",
            "Use static_scan_findings for detailed scanner results",
        ],
    )


# ---------------------------------------------------------------------------
# Resources — read-only access to analysis artifacts
# ---------------------------------------------------------------------------


@mcp.resource("analysis://{repo_path*}/context")
def read_context(repo_path: str) -> str:
    """Read the CONTEXT.md narrated architecture overview for a repository.

    This is the primary human-readable output of the analysis — a markdown
    document covering architecture, business logic, key components,
    and risks. Best artifact to read first for codebase understanding.
    """
    return _read_artifact(f"/{repo_path}", "CONTEXT.md")


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
    generated file list, and bundle metadata.
    """
    return _read_artifact(f"/{repo_path}", "analysis_result.json")
