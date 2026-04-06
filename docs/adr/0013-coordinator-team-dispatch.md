# ADR-0013: Coordinator + Team Dispatch Architecture

**Date**: 2026-04-06

**Status**: accepted (supersedes [ADR-0012](0012-strands-swarm-multi-agent.md))

## Context

The v8 architecture ([ADR-0012](0012-strands-swarm-multi-agent.md)) used a fixed 4-node sequential Strands Swarm pipeline (`structure_analyst -> history_analyst -> code_reader -> synthesizer`). This had three limitations:

- **Fixed team structure**: Every codebase got the same 4-node pipeline regardless of size, language mix, or risk profile. A 50-file utility library received the same treatment as a 5000-file monorepo.
- **No parallelism within the swarm**: Nodes executed sequentially, so the total wall-clock time was the sum of all node durations. History analysis could not overlap with structure analysis even though they are independent.
- **Context window saturation**: Findings accumulated sequentially through `SharedContext` text handoff. By the time the synthesizer ran, earlier structure findings were compressed or lost, degrading output quality.

Meanwhile, the deterministic indexer ([ADR-0011](0011-deterministic-indexer.md)) now produces a `heuristic_summary.json` that characterizes the codebase (file count, language mix, GitNexus community count, security findings, complexity metrics). This makes it possible for an LLM to plan an appropriate team structure dynamically.

## Decision

Replace the fixed 4-node Swarm with a single **Coordinator Agent** (a regular `strands.Agent`, not a Swarm node) that reads the heuristic summary, plans teams dynamically, dispatches parallel Swarm teams, and consolidates findings into narrative bundles.

Key implementation details:

- **Coordinator agent** (`src/code_context_agent/agent/coordinator.py`): Created via `create_coordinator_agent()`. Receives all analysis tools plus 6 coordinator-specific tools. Uses `structured_output_model=AnalysisResult` for typed output. System prompt rendered from a Jinja2 template (`templates/coordinator.md.j2`, ~150 lines in the main file, ~590 lines after rendering 11 included partials and steering directives) that embeds heuristic summary metrics.
- **Six coordinator tools** (`src/code_context_agent/tools/coordinator_tools.py`): `dispatch_team`, `read_team_findings`, `write_bundle`, `read_heuristic_summary`, `score_narrative`, `enrich_bundle`. Tool docstrings encode all behavioral guidance (team sizing heuristics, multi-wave patterns, bundle structure) so the coordinator prompt stays lean.
- **`dispatch_team`** creates a Strands Swarm on-the-fly via `strands_tools.swarm`. Each team gets 2-3 agents with scoped tool subsets resolved from the coordinator's tool registry. Teams run with configurable `execution_timeout` and `node_timeout` (defaults scale with analysis mode: standard vs. full).
- **Multi-wave pattern**: Wave 1 (scout) dispatches lightweight teams with broad tools (`gitnexus_query`, `git_hotspots`, `rg_search`) and short timeouts (2-3 min). Wave 2 (deep-dive) dispatches targeted teams with full tools (`gitnexus_impact`, `read_file_bounded`, `git_blame_summary`) and longer timeouts (5-8 min), only for areas flagged by scouts. Wave 3 (synthesis) consolidates all findings. Small repos (<200 files) collapse into a single wave.
- **File-based handoff**: Teams write findings to `.code-context/tmp/teams/{team_id}/findings.md` and `metadata.json`. The coordinator reads them via `read_team_findings`. This is resilient to team failures (partial results are preserved) and avoids context window bloat from in-memory handoff.
- **Dynamic team sizing**: The coordinator plans teams based on heuristic summary signals: codebase volume, GitNexus community count, security findings severity, complexity scores, and optional `--focus` flag. Sizing heuristics are encoded in the `dispatch_team` docstring.
- **Quality feedback loop**: `score_narrative` scores bundle quality on 5 dimensions (specificity, structure, diagrams, depth, cross-references). If total score < 3.5, `enrich_bundle` triggers a chain-of-density rewrite.
- **Conversation management**: Uses `SummarizingConversationManager` (summary_ratio=0.3, preserve_recent_messages=10) to handle long coordinator conversations without context window overflow.
- **Runner** (`src/code_context_agent/agent/runner.py`): Invokes the coordinator via `coordinator.invoke_async()`. Auto-indexes if no heuristic summary exists. Supports `bundles_only` mode to regenerate bundles from existing team findings.

## Consequences

**Positive:**

- Teams execute in parallel, reducing wall-clock time for multi-area analysis (limited by the slowest team, not the sum)
- Team structure adapts to codebase characteristics — a 100-file project gets 1 team; a 3000-file monorepo gets 5+ domain-scoped teams
- File-based handoff is resilient: if a team fails or times out, its partial findings are still available; other teams are unaffected
- Each team gets a focused mandate and scoped tool subset, reducing context pollution
- The coordinator prompt delegates behavioral guidance to tool docstrings, making it easier to evolve rules without touching the prompt template
- The multi-wave pattern (scout then deep-dive) avoids wasting deep-read time on areas that turn out to be simple
- Quality scoring and enrichment create a feedback loop that improves bundle output without manual intervention

**Negative:**

- More complex orchestration: the coordinator must plan, dispatch, wait, cross-reference, and synthesize — a longer cognitive chain than a fixed pipeline
- Module-level state in `coordinator_tools.py` (`_output_dir`, `_repo_path`, `_tool_registry`, timeouts) must be configured before agent creation via `configure()`, creating an implicit initialization dependency
- Total token usage increases further vs. ADR-0012 (coordinator context + N team contexts), though each individual context is smaller and more focused
- Team naming and mandate quality depends on the coordinator LLM's planning ability — poor plans lead to redundant or incomplete coverage

**Neutral:**

- The `strands_tools.swarm` function is reused for team execution, but teams are now ephemeral (created per-dispatch) rather than statically defined
- `create_agent()` in `factory.py` is no longer used; `get_analysis_tools()` provides the shared tool list that both coordinator and teams use
- HookProviders from `hooks.py` apply to the coordinator agent only; team agents inherit default behavior from `strands_tools.swarm`
