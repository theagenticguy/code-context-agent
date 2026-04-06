"""Coordinator-level tools for team dispatch, finding reads, and bundle writing.

These tools are used ONLY by the coordinator agent, not by team agents.
Their docstrings encode all behavioral guidance so the coordinator prompt stays lean.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path  # noqa: TC003 — used at runtime for _output_dir/_repo_path
from typing import Any

from loguru import logger
from strands import tool

# ---------------------------------------------------------------------------
# Module-level state — configured by coordinator.py before agent creation.
# Follows the same pattern as tools/graph/tools.py (_graphs dict).
# ---------------------------------------------------------------------------
_output_dir: Path | None = None
_repo_path: Path | None = None
_tool_registry: dict[str, Any] = {}  # tool_name → tool function, populated by configure()
_execution_timeout: float | None = None
_node_timeout: float | None = None


def configure(
    output_dir: Path,
    repo_path: Path,
    tools: list[Any] | None = None,
    *,
    execution_timeout: float,
    node_timeout: float,
) -> None:
    """Set the output directory, repo path, tool registry, and timeout defaults.

    Must be called before the coordinator agent is created.

    Args:
        output_dir: Path to .code-context output directory.
        repo_path: Path to the repository root.
        tools: List of tool functions from get_analysis_tools(). Used by dispatch_team
               to resolve string tool names to actual function objects for swarm agents.
        execution_timeout: Default max seconds for entire team execution.
        node_timeout: Default max seconds per agent node within a team.
    """
    global _output_dir, _repo_path, _tool_registry, _execution_timeout, _node_timeout  # noqa: PLW0603
    _output_dir = output_dir
    _repo_path = repo_path
    _execution_timeout = execution_timeout
    _node_timeout = node_timeout
    if tools:
        _tool_registry = {}
        for t in tools:
            # strands @tool-decorated functions have a tool_name attribute
            name = getattr(t, "tool_name", None) or getattr(t, "__name__", None)
            if name:
                _tool_registry[name] = t


def _get_output_dir() -> Path:
    if _output_dir is None:
        msg = "coordinator_tools.configure() must be called before using coordinator tools"
        raise RuntimeError(msg)
    return _output_dir


def _teams_dir() -> Path:
    return _get_output_dir() / "tmp" / "teams"


def _bundles_dir() -> Path:
    return _get_output_dir() / "bundles"


# ============================================================================
# Tool 1: dispatch_team
# ============================================================================


@tool
def dispatch_team(
    team_id: str,
    mandate: str,
    agents: list[dict[str, Any]],
    file_scope: list[str] | None = None,
    key_questions: list[str] | None = None,
    artifact_pointers: list[str] | None = None,
    max_handoffs: int = 10,
    execution_timeout: float | None = None,
    node_timeout: float | None = None,
) -> str:
    """Dispatch a specialist team to investigate a specific area of the codebase.

    Each team runs as a Strands Swarm — a group of 2-3 agents that hand off to
    each other to complete a mandate. Teams write their findings to a persistent
    file at .code-context/tmp/teams/{team_id}/findings.md so you can read them
    later with read_team_findings.

    TEAM SIZING HEURISTICS (based on heuristic_summary.json):

      Volume + Structure           | Strategy
      -----------------------------|------------------------------------------
      <200 files, <5 communities   | 1 team total, 2 agents (analyst + reader)
      200-2000, 5-15 communities   | 1 team per major community (2-4 teams)
      2000+, 15+ communities       | Top 5 communities get dedicated teams
      gitnexus.process_count > 50  | Add cross-cutting team for shared processes
      --focus set                  | 1 dedicated focus team scoped to focus community
      health.semgrep critical > 0  | MANDATORY security team regardless of size

    AGENT SPEC FORMAT:

      Each entry in `agents` is a dict with:
        - name (str): e.g. "structure_analyst", "code_reader"
        - system_prompt (str): role and instructions for this agent
        - tools (list[str]): tool names this agent can use, inherited from
          the coordinator's tool registry. Common subsets:

          Structure: gitnexus_query, gitnexus_context, gitnexus_impact,
                     gitnexus_cypher, rg_search, bm25_search, read_file_bounded
          Git:       git_hotspots, git_files_changed_together, git_blame_summary,
                     git_file_history, git_contributors, git_recent_commits,
                     read_file_bounded
          Reading:   read_file_bounded, rg_search, bm25_search, gitnexus_context,
                     gitnexus_query

    MULTI-WAVE PATTERN:

      Wave 1 (Scout): 2-agent teams with light tools (gitnexus_query, git_hotspots, rg_search).
        Mandate: "Survey area X. Flag complexity, cross-cutting concerns, key symbols."
        Timeout: 2-3 min per team. Use execution_timeout=180.

      Wave 2 (Deep): 2-3 agent teams with full tools (gitnexus_context, gitnexus_impact, read_file_bounded).
        Mandate: "Deep investigation of area X based on scout findings: [paste key findings]."
        Timeout: 5-8 min per team. Use execution_timeout=480. Only dispatch for flagged areas.

      Small repos (<200 files): collapse into a single wave with all tools.

    FINDING PERSISTENCE:

      The team task is automatically augmented to require writing findings to:
        .code-context/tmp/teams/{team_id}/findings.md
        .code-context/tmp/teams/{team_id}/metadata.json

      metadata.json schema: {"files_read": [...], "tools_used": [...],
                              "duration_s": N, "status": "done"}

    Args:
        team_id: Unique identifier (e.g., "team-structure", "team-focus-auth").
        mandate: What to investigate and why (1-3 sentences).
        agents: List of agent spec dicts (see AGENT SPEC FORMAT above).
        file_scope: Optional file paths or directories to focus on.
        key_questions: Optional questions the coordinator wants answered.
        artifact_pointers: Optional Phase 1 artifact paths to consult.
        max_handoffs: Max handoffs between agents within the team.
        execution_timeout: Max seconds for the entire team execution.
            Omit to use the configured default (scales with analysis mode).
        node_timeout: Max seconds per individual agent turn.
            Omit to use the configured default (scales with analysis mode).

    Returns:
        JSON with team_id, status, findings_path, and result summary.
    """
    from strands_tools.swarm import swarm as _swarm

    # Apply configured defaults when the coordinator omits explicit timeouts
    configured_exec = _execution_timeout
    configured_node = _node_timeout
    if configured_exec is None or configured_node is None:
        msg = "coordinator_tools.configure() must be called before using coordinator tools"
        raise RuntimeError(msg)
    effective_exec_timeout = execution_timeout if execution_timeout is not None else configured_exec
    effective_node_timeout = node_timeout if node_timeout is not None else configured_node

    agent_names = [a.get("name", "?") for a in agents]
    logger.debug(
        f"dispatch_team({team_id}): execution_timeout={effective_exec_timeout}s, "
        f"node_timeout={effective_node_timeout}s, agents={agent_names}",
    )

    output_dir = _get_output_dir()

    # Resolve string tool names in agent specs to actual tool functions.
    # strands_tools.swarm expects tool function objects, not string names.
    resolved_agents = []
    for agent_spec in agents:
        spec = dict(agent_spec)  # don't mutate the original
        if "tools" in spec and isinstance(spec["tools"], list):
            resolved_tools = []
            for tool_name in spec["tools"]:
                if isinstance(tool_name, str) and tool_name in _tool_registry:
                    resolved_tools.append(_tool_registry[tool_name])
                else:
                    resolved_tools.append(tool_name)  # already a function or unknown
            spec["tools"] = resolved_tools
        resolved_agents.append(spec)

    # Create team directory
    team_dir = _teams_dir() / team_id
    team_dir.mkdir(parents=True, exist_ok=True)

    findings_path = str(team_dir / "findings.md")
    metadata_path = str(team_dir / "metadata.json")

    # Build augmented task with persistence instructions
    task_parts = [
        f"## Team Mandate\n{mandate}\n",
    ]

    if file_scope:
        scope_list = "\n".join(f"- {f}" for f in file_scope)
        task_parts.append(f"## File Scope\nFocus on these files/directories:\n{scope_list}")

    if key_questions:
        task_parts.append("## Key Questions\n" + "\n".join(f"- {q}" for q in key_questions))

    if artifact_pointers:
        task_parts.append(
            "## Pre-computed Artifacts\nConsult these Phase 1 artifacts for context:\n"
            + "\n".join(f"- {a}" for a in artifact_pointers),
        )

    task_parts.append(
        f"""## Required Output

When your analysis is complete, the LAST agent in the chain MUST:

1. Write detailed findings to: {findings_path}
   - Use markdown format with clear sections
   - Include file:line references for all claims
   - Use mermaid code-fenced diagrams (never ASCII art)

2. Write metadata to: {metadata_path}
   - JSON with keys: files_read (list), tools_used (list), duration_s (float), status ("done")

Use the write_file tool for both files. The coordinator will read these after your team completes.

Use gitnexus_query/gitnexus_context/gitnexus_impact for structural code intelligence.
Output directory: {output_dir}
Repository: {_repo_path}""",
    )

    augmented_task = "\n\n".join(task_parts)

    start = time.monotonic()
    try:
        result = _swarm(
            task=augmented_task,
            agents=resolved_agents,
            max_handoffs=max_handoffs,
            max_iterations=max_handoffs,
            execution_timeout=effective_exec_timeout,
            node_timeout=effective_node_timeout,
        )
        duration = time.monotonic() - start
        status = "completed"
        summary = str(result)[:500] if result else "No result returned"
    except Exception as e:  # noqa: BLE001
        duration = time.monotonic() - start
        status = "error"
        summary = str(e)[:500]
        logger.warning(f"Team {team_id} failed after {duration:.1f}s: {e}")

    # Append structured debug entry to team_debug.jsonl
    debug_entry = {
        "team_id": team_id,
        "status": status,
        "duration_seconds": round(duration, 1),
        "execution_timeout": effective_exec_timeout,
        "node_timeout": effective_node_timeout,
        "agents": agent_names,
        "agent_count": len(agents),
        "mandate_preview": mandate[:200],
    }
    try:
        debug_log = _teams_dir() / "team_debug.jsonl"
        with debug_log.open("a") as f:
            f.write(json.dumps(debug_entry) + "\n")
    except OSError as e:
        logger.debug(f"Failed to write team_debug.jsonl: {e}")

    return json.dumps(
        {
            "team_id": team_id,
            "status": status,
            "duration_seconds": round(duration, 1),
            "findings_path": findings_path,
            "metadata_path": metadata_path,
            "summary": summary,
        },
    )


# ============================================================================
# Tool 2: read_team_findings
# ============================================================================


@tool
def read_team_findings(team_id: str | None = None) -> str:
    """Read findings from dispatched teams.

    If team_id is None, lists all team directories with their status and
    metadata summary — use this to see which teams have completed.

    If team_id is specified, returns that team's full findings.md content.

    CROSS-REFERENCING PATTERN:

      After reading all team findings, look for files or symbols mentioned
      by multiple teams. Convergent signals from independent teams are
      high-confidence findings. Divergent signals indicate areas that need
      a follow-up investigation.

    Args:
        team_id: Specific team to read, or None to list all teams.

    Returns:
        JSON listing all teams (when team_id=None), or the findings
        markdown content (when team_id is specified).
    """
    teams_root = _teams_dir()

    if team_id is None:
        # List all teams
        if not teams_root.exists():
            return json.dumps({"status": "no_teams", "teams": []})

        teams = []
        for team_dir in sorted(teams_root.iterdir()):
            if not team_dir.is_dir():
                continue
            meta_path = team_dir / "metadata.json"
            findings_path = team_dir / "findings.md"
            meta = None
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                except (json.JSONDecodeError, OSError):
                    pass  # Corrupt or unreadable metadata — skip this team's metadata

            teams.append(
                {
                    "team_id": team_dir.name,
                    "has_findings": findings_path.exists(),
                    "findings_lines": len(findings_path.read_text().splitlines()) if findings_path.exists() else 0,
                    "metadata": meta,
                },
            )

        return json.dumps({"status": "ok", "teams": teams}, indent=2)

    # Read specific team
    team_dir = teams_root / team_id
    if not team_dir.exists():
        return json.dumps({"status": "error", "message": f"Team directory not found: {team_id}"})

    findings_path = team_dir / "findings.md"
    if not findings_path.exists():
        return json.dumps(
            {
                "status": "no_findings",
                "message": f"Team {team_id} has no findings.md — it may still be running or failed before writing.",
            },
        )

    content = findings_path.read_text()
    return json.dumps(
        {
            "status": "ok",
            "team_id": team_id,
            "findings": content,
            "line_count": len(content.splitlines()),
        },
    )


# ============================================================================
# Tool 3: write_bundle
# ============================================================================


@tool
def write_bundle(area: str, content: str, is_context: bool = False) -> str:
    """Write a narrative bundle or the executive summary CONTEXT.md.

    BUNDLE NAMING:
      - Bundles go to: .code-context/bundles/BUNDLE.{area}.md
      - CONTEXT.md goes to: .code-context/CONTEXT.md (set is_context=True)

    BUNDLE STRUCTURE (7 sections):
      1. One-paragraph summary — what this area does in business terms
      2. Key files — ranked list with role descriptions and file:line ranges
      3. Call flow — how data/control flows through this area (use mermaid, informed by gitnexus_context/gitnexus_query)
      4. Blast radius — what breaks if you change this area
      5. Risk assessment — security, complexity, coupling, test coverage
      6. Change guidance — where to start, what to watch out for
      7. Git context — ownership, churn frequency, implicit coupling

    BUNDLE SELECTION LOGIC:
      - If --focus was specified: MANDATORY bundle for the focus area
      - Always generate preemptive bundles for:
        * High blast radius areas (extreme fan-in/fan-out)
        * Hot spots (high churn + high complexity)
        * Critical business logic (core domain, not glue code)

    DIAGRAM RULE:
      All diagrams MUST use mermaid code-fenced blocks. Never ASCII art.

    Args:
        area: Bundle area identifier (e.g., "auth", "hotspots", "security").
              Ignored when is_context=True.
        content: The full markdown content to write.
        is_context: If True, writes CONTEXT.md instead of a bundle file.

    Returns:
        JSON with the written file path and line count.
    """
    output_dir = _get_output_dir()

    if is_context:
        file_path = output_dir / "CONTEXT.md"
    else:
        bundles_dir = _bundles_dir()
        bundles_dir.mkdir(parents=True, exist_ok=True)
        file_path = bundles_dir / f"BUNDLE.{area}.md"

    file_path.write_text(content)
    line_count = len(content.splitlines())

    logger.info(f"Wrote {file_path.name}: {line_count} lines")

    return json.dumps(
        {
            "status": "ok",
            "path": str(file_path),
            "relative_path": str(file_path.relative_to(output_dir)),
            "line_count": line_count,
        },
    )


# ============================================================================
# Tool 4: read_heuristic_summary
# ============================================================================


@tool
def read_heuristic_summary() -> str:
    """Read the pre-computed heuristic summary produced by the deterministic indexer.

    This artifact is the ONLY thing you need to read before planning teams.
    It summarizes 21 indexer steps into a compact JSON structure.

    SCHEMA:

      volume:
        total_files, total_lines, estimated_tokens, languages (dict), frameworks (list)

      health:
        semgrep_findings: {critical, high, medium, low, info}
        owasp_findings: {category: count}
        type_errors: int
        lint_violations: int
        dead_code_symbols: int
        clone_groups: int
        avg_cyclomatic_complexity: float

      gitnexus:
        indexed: bool              — whether GitNexus has indexed this repo
        repo_name: str             — the repo identifier in the GitNexus graph
        community_count: int       — number of functional communities detected
        process_count: int         — number of execution flows traced
        symbol_count: int          — total symbols in the knowledge graph
        edge_count: int            — total relationships
        top_communities: list      — [{name, symbols, cohesion}, ...]

      git:
        total_commits_analyzed, active_contributors
        most_coupled_pairs: list of {a, b, coupling}

      mcp:
        context7_available: bool   — whether context7 library docs tool is available

    INTERPRETATION GUIDE:

      Signal                               | Action
      -------------------------------------|---------------------------------------
      health.semgrep_findings.critical > 0 | MANDATORY security team
      gitnexus.indexed is True             | Use gitnexus_impact for blast radius
      health.avg_cyclomatic_complexity > 10| Complexity team for deep code reading
      volume.total_files > 2000            | Domain-scoped teams, not one mega-team
      gitnexus.community_count > 15        | Top 5 communities get dedicated teams
      gitnexus.process_count > 50          | Add cross-cutting team for shared processes
      git.most_coupled_pairs coupling > 0.7| Implicit coupling — needs investigation

    Returns:
        The heuristic_summary.json content as formatted JSON.
        Falls back to index_metadata.json if heuristic summary is unavailable.
    """
    output_dir = _get_output_dir()

    heuristic_path = output_dir / "heuristic_summary.json"
    if heuristic_path.exists():
        try:
            data = json.loads(heuristic_path.read_text())
            return json.dumps(data, indent=2)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read heuristic summary: {e}")

    # Fallback to index metadata
    metadata_path = output_dir / "index_metadata.json"
    if metadata_path.exists():
        try:
            data = json.loads(metadata_path.read_text())
            return json.dumps({"_fallback": "index_metadata", **data}, indent=2)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read index metadata: {e}")

    return json.dumps({"status": "error", "message": "No heuristic summary or index metadata found"})


# ============================================================================
# Tool 5: score_narrative
# ============================================================================

# Scoring thresholds: (upper_bound_exclusive, score) pairs evaluated in order.
_SPECIFICITY_THRESHOLDS = [(5, 1.0), (10, 2.0), (20, 3.0), (30, 4.0)]
_STRUCTURE_THRESHOLDS = [(3, 1.0), (5, 2.0), (8, 3.0), (11, 4.0)]
_DEPTH_THRESHOLDS = [(20, 1.0), (50, 2.0), (100, 3.0), (200, 4.0)]
_XREF_THRESHOLDS = [(3, 1.0), (8, 2.0), (15, 3.0), (25, 4.0)]

_FILE_LINE_RE = re.compile(r"\w+\.\w+:\d+")
_HEADING_RE = re.compile(r"^#{2,3}\s", re.MULTILINE)
_MERMAID_RE = re.compile(r"```mermaid", re.IGNORECASE)
# Match paths like src/foo/bar.py, ./utils/helpers.ts, foo_bar.rs — at least one slash.
_FILE_PATH_RE = re.compile(r"(?:\.?/)?(?:[\w.-]+/)+[\w.-]+\.\w+")

_REVISION_THRESHOLD = 3.5


def _score_by_thresholds(count: int, thresholds: list[tuple[int, float]], max_score: float = 5.0) -> float:
    """Return a score for *count* using ascending (upper_bound, score) thresholds."""
    for upper, score in thresholds:
        if count < upper:
            return score
    return max_score


@tool
def score_narrative(bundle_area: str) -> str:
    """Score a narrative bundle's quality on multiple dimensions.

    Call this after write_bundle to evaluate quality. If total score < 3.5,
    call enrich_bundle to improve it.

    Scoring dimensions (each 0.0-5.0):
      - specificity: density of file:line references
      - structure: number of markdown headings (## and ###)
      - diagrams: presence of mermaid code blocks
      - depth: total line count
      - cross_references: unique file paths mentioned

    Args:
        bundle_area: The bundle area to score (e.g., 'auth', 'hotspots').

    Returns:
        JSON with area, per-dimension scores, total average, needs_revision flag, and suggestions.
    """
    bundle_path = _bundles_dir() / f"BUNDLE.{bundle_area}.md"
    if not bundle_path.exists():
        return json.dumps({"status": "error", "message": f"Bundle not found: {bundle_path}"})

    content = bundle_path.read_text()

    # --- Specificity: file:line references ---
    file_line_count = len(_FILE_LINE_RE.findall(content))
    specificity = _score_by_thresholds(file_line_count, _SPECIFICITY_THRESHOLDS)

    # --- Structure: markdown headings ---
    heading_count = len(_HEADING_RE.findall(content))
    structure = _score_by_thresholds(heading_count, _STRUCTURE_THRESHOLDS)

    # --- Diagrams: mermaid blocks ---
    mermaid_count = len(_MERMAID_RE.findall(content))
    if mermaid_count == 0:
        diagrams = 1.0
    elif mermaid_count == 1:
        diagrams = 3.0
    else:
        diagrams = 5.0

    # --- Depth: line count ---
    line_count = len(content.splitlines())
    depth = _score_by_thresholds(line_count, _DEPTH_THRESHOLDS)

    # --- Cross-references: unique file paths ---
    unique_paths = len(set(_FILE_PATH_RE.findall(content)))
    cross_references = _score_by_thresholds(unique_paths, _XREF_THRESHOLDS)

    scores = {
        "specificity": specificity,
        "structure": structure,
        "diagrams": diagrams,
        "depth": depth,
        "cross_references": cross_references,
    }
    total = sum(scores.values()) / len(scores)
    needs_revision = total < _REVISION_THRESHOLD

    suggestions: list[str] = []
    if specificity <= 2.0:
        suggestions.append(f"Add more file:line references (currently {file_line_count}).")
    if structure <= 2.0:
        suggestions.append(f"Add more section headings for structure (currently {heading_count}).")
    if diagrams <= 1.0:
        suggestions.append("Add at least one mermaid diagram for call flow or architecture.")
    if depth <= 2.0:
        suggestions.append(f"Expand content depth (currently {line_count} lines).")
    if cross_references <= 2.0:
        suggestions.append(f"Cross-reference more files/modules (currently {unique_paths} unique paths).")

    return json.dumps(
        {
            "area": bundle_area,
            "scores": scores,
            "total": round(total, 2),
            "needs_revision": needs_revision,
            "suggestions": suggestions,
        },
    )


# ============================================================================
# Tool 6: enrich_bundle
# ============================================================================


@tool
def enrich_bundle(bundle_area: str, feedback: str) -> str:
    """Read an existing bundle and prepare enrichment context.

    Call this when score_narrative indicates revision needed (total < 3.5).
    Returns the current bundle content together with the feedback so you
    can rewrite it with improvements via write_bundle.

    ENRICHMENT PATTERN (Chain-of-Density):
      1. Call score_narrative to identify weak dimensions.
      2. Call enrich_bundle with the suggestions as feedback.
      3. Rewrite the bundle incorporating the feedback via write_bundle.
      4. Optionally re-score to verify improvement.

    Args:
        bundle_area: The bundle area to enrich (e.g., 'auth', 'hotspots').
        feedback: Specific feedback from score_narrative about what to improve.

    Returns:
        JSON with the current bundle content, line count, and the feedback for rewriting.
    """
    bundle_path = _bundles_dir() / f"BUNDLE.{bundle_area}.md"
    if not bundle_path.exists():
        return json.dumps({"status": "error", "message": f"Bundle not found: {bundle_path}"})

    content = bundle_path.read_text()

    return json.dumps(
        {
            "status": "ok",
            "area": bundle_area,
            "current_content": content,
            "line_count": len(content.splitlines()),
            "feedback": feedback,
            "instruction": (
                "Rewrite this bundle incorporating the feedback above. "
                "Use write_bundle to save the improved version. "
                "Preserve all existing accurate information while adding depth."
            ),
        },
    )
