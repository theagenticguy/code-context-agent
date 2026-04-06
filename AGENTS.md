# code-context-agent

AI-powered CLI tool that analyzes codebases and produces structured context
documentation for AI coding assistants.

## Architecture

Two-stage pipeline: deterministic index (16 steps, ~30-90s) → Coordinator Agent dispatches parallel Swarm teams → structured output with narrative bundles.
Hook-driven display (Rich TUI or JSON logs). No AG-UI dependency.

```
CLI (cyclopts) → index (deterministic, ~30-90s)
                    ├── GitNexus analyze (structural code graph)
                    ├── git hotspot + co-change analysis
                    ├── repomix signatures + orientation
                    ├── static scanners (semgrep, typecheck, lint, complexity, dead code)
                    └── heuristic_summary.json (compact metrics for coordinator)

              → analyze (Coordinator, ~5-15 min)
                    ├── read_heuristic_summary → plan teams
                    ├── dispatch_team("team-structure", ...) ┐
                    ├── dispatch_team("team-history", ...)    ├ parallel Swarm teams
                    ├── dispatch_team("team-reader", ...)     ┘
                    ├── read_team_findings → cross-reference
                    ├── write_bundle → CONTEXT.md + BUNDLE.{area}.md
                    ├── HookProvider-driven display (TUI or JSON logs)
                    └── AnalysisResult (structured output with bundles)

Deterministic Indexer (code-context-agent index)
    ├── GitNexus analyze (Tree-sitter parsing, clustering, process tracing)
    ├── Git hotspot + co-change JSON output
    ├── Repomix signatures + orientation
    ├── Static scanners (semgrep, typecheck, lint, complexity, dead code)
    └── heuristic_summary.json (bridge to coordinator)

FastMCP v3 Server (code-context-agent serve)
    ├── start_analysis / check_analysis (kickoff/poll)
    ├── git_evolution (hotspots, coupling, contributors)
    ├── static_scan_findings (semgrep, typecheck, lint, complexity, dead code)
    ├── heuristic_summary (compact index metrics)
    ├── list_repos
    └── 5 resource templates (analysis artifacts)

Multi-Repo Registry (~/.code-context/registry.json)
    └── list_repos MCP tool
```

### Key source locations

| Path | What |
|------|------|
| `src/code_context_agent/cli.py` | CLI entry point: `analyze`, `serve` commands |
| `src/code_context_agent/config.py` | Settings via pydantic-settings, `CODE_CONTEXT_` prefix |
| `src/code_context_agent/agent/coordinator.py` | Coordinator agent factory: tools, model, heuristic summary, lean prompt |
| `src/code_context_agent/agent/factory.py` | Analysis tool collection + GitNexus/context7 MCP providers |
| `src/code_context_agent/agent/runner.py` | Analysis runner with coordinator invocation + hook-based display |
| `src/code_context_agent/agent/hooks.py` | HookProviders: quality, compaction, tool efficiency, reasoning, fail-fast, team dispatch, display |
| `src/code_context_agent/tools/coordinator_tools.py` | 6 coordinator tools: `dispatch_team`, `read_team_findings`, `write_bundle`, `read_heuristic_summary`, `score_narrative`, `enrich_bundle` |
| `src/code_context_agent/consumer/phases.py` | 5-phase `AnalysisPhase` enum and tool-to-phase mapping |
| `src/code_context_agent/mcp/server.py` | FastMCP v3 server (complementary to GitNexus) |
| `src/code_context_agent/tools/discovery.py` | ripgrep, repomix tools |
| `src/code_context_agent/tools/git.py` | Git history analysis tools |
| `src/code_context_agent/tools/search/` | BM25 ranked text search |
| `src/code_context_agent/indexer.py` | Deterministic index pipeline (GitNexus + git + static scanners) |
| `src/code_context_agent/mcp/registry.py` | Multi-repo registry with lazy graph cache |
| `src/code_context_agent/templates/` | Jinja2 prompts: `coordinator.md.j2` (~35 lines), partials/, steering/. Rendering in `templates/__init__.py` |
| `src/code_context_agent/models/output.py` | AnalysisResult, Bundle, BusinessLogicItem, ArchitecturalRisk, RefactoringCandidate, CodeHealthMetrics |

### Tool categories (~25+)

- **Coordinator** (6): `dispatch_team`, `read_team_findings`, `write_bundle`, `read_heuristic_summary`, `score_narrative`, `enrich_bundle`
- **Discovery** (12): `create_file_manifest`, `repomix_orientation`, `repomix_bundle`, `repomix_bundle_with_context`, `repomix_compressed_signatures`, `repomix_json_export`, `repomix_split_bundle`, `rg_search`, `write_file`, `write_file_list`, `read_file_bounded`
- **Search** (1): `bm25_search` (BM25 ranked text search via rank_bm25)
- **Git** (7): `git_hotspots`, `git_files_changed_together`, `git_blame_summary`, `git_file_history`, `git_contributors`, `git_recent_commits`, `git_diff_file`
- **Shell** (1): `shell`
- **Orchestration** (1): `graph` (from strands_tools, multi-agent DAG)
- **GitNexus MCP** (6+): `gitnexus_query`, `gitnexus_context`, `gitnexus_impact`, `gitnexus_detect_changes`, `gitnexus_cypher`, `gitnexus_list_repos`
- **context7 MCP**: `context7_resolve-library-id`, `context7_query-docs`
- **MCP Server** (6): `start_analysis`, `check_analysis`, `list_repos`, `git_evolution`, `static_scan_findings`, `heuristic_summary`. All responses include contextual `next_steps` hints.

### State management

- **Team findings**: File-based at `.code-context/tmp/teams/{team_id}/findings.md` + `metadata.json`
- **Heuristic summary**: `.code-context/heuristic_summary.json` (bridge between indexer and coordinator)
- **Coordinator tools config**: Module-level `_output_dir`, `_repo_path`, `_tool_registry` in `tools/coordinator_tools.py`
- **GitNexus**: GitNexus MCP server lifecycle managed by strands MCPClient in factory.py
- **MCP jobs**: Module-level `_jobs` dict in `mcp/server.py` for kickoff/poll pattern
- **Registry**: `~/.code-context/registry.json` with lazy graph cache (5-min TTL) in `mcp/registry.py`
- **BM25 index cache**: Module-level `_indexes` dict in `tools/search/`
- **Config**: Cached singleton via `get_settings()` with `@lru_cache`

## Patterns and conventions

### Tools use the `@tool` decorator from strands

```python
from strands import tool

@tool
def my_tool(param: str, option: int = 10) -> str:
    """Docstring becomes the tool description for the LLM.

    Args:
        param: Description used by the LLM for parameter understanding.
        option: Description with default shown.
    """
    return json.dumps({"status": "success", "result": ...})
```

All tools return JSON strings. Error responses use `{"status": "error", "message": "..."}`.

### MCP tools use `@mcp.tool` from FastMCP v3

```python
from fastmcp import FastMCP
from typing import Annotated
from pydantic import Field

mcp = FastMCP("server-name")

@mcp.tool
def my_mcp_tool(
    param: Annotated[str, Field(description="Description for AI")],
) -> dict:
    """First line = tool summary for search indexing.

    USE THIS WHEN: ...
    PREREQUISITE: ...

    Returns:
        {"key": "value", ...}
    """
    return {"key": "value"}
```

MCP tools return dicts (FastMCP handles serialization). Include `USE THIS WHEN` /
`DO NOT USE IF` in docstrings so AI assistants know when to select the tool.

### Imports inside functions to avoid circular imports

The `factory.py` imports all tool modules inside `get_analysis_tools()` rather
than at module level. Follow this pattern when adding new tool modules.

### Pydantic models use custom base classes

- `FrozenModel`: Immutable, for data transfer (output models, graph nodes/edges)
- `StrictModel`: Mutable, for internal state

Both are in `models/base.py`. Use `FrozenModel` for new data models.

## Development

### Prerequisites

- Python 3.13+ (managed via `mise`)
- Node.js 22+ (managed via `mise`)
- `uv` for Python package management
- External CLIs: `rg` (ripgrep), `repomix`, `npx` (for context7), `gitnexus` (GitNexus CLI for code graph indexing)
- AWS credentials configured for Bedrock access

### Commands

| Task | Command |
|------|---------|
| Install all deps | `mise run install:all` |
| Install Python deps | `mise run install` |
| Run CLI | `uv run code-context-agent` |
| Analyze a repo | `uv run code-context-agent analyze /path/to/repo` |
| Analyze (bundles only) | `uv run code-context-agent analyze /path --bundles-only` |
| Index a repo | `uv run code-context-agent index /path/to/repo` |
| Start MCP server | `uv run code-context-agent serve` |
| Lint (Python) | `mise run lint` |
| Format (Python) | `mise run format` |
| Type check (Python) | `mise run typecheck` |
| Test | `mise run test` |
| All checks | `mise run check` |
| Build | `mise run build` |
| Commit | `uv run cz commit` |
| Bump + tag | `uv run cz bump` then `git push origin <tag>` |

### Git hooks (lefthook)

Hooks are enforced automatically. Do not skip them.

- **pre-commit**: ruff check+fix, ruff format, ty check, betterleaks
- **commit-msg**: conventional commit validation via commitizen
- **pre-push**: lint, format-check, typecheck, test, betterleaks, semgrep OWASP

### Conventional commits

All commits must follow conventional commit format. Commitizen enforces this.

- `feat:` → MINOR bump
- `fix:` → PATCH bump
- `feat!:` or `BREAKING CHANGE:` footer → MAJOR bump
- `docs:`, `chore:`, `refactor:`, `test:`, `ci:` → no version bump

**Important**: Do not include `BREAKING CHANGE:` in the commit body unless there
is an actual breaking change. Commitizen parses it literally and will trigger a
MAJOR version bump.

After `cz bump`, push the tag explicitly: `git push origin v<version>` (commitizen
creates lightweight tags, `--follow-tags` only pushes annotated tags).

### Code style

- Line length: 120
- Python 3.13+ typing: `list[str]` not `List[str]`, `X | None` not `Optional[X]`
- Google-style docstrings
- `pathlib.Path` over `os.path`
- `from __future__ import annotations` in all modules

### Testing

- `pytest` with `asyncio_mode = "auto"`
- Tests in `tests/` mirroring `src/` structure
- Graph model and analysis have thorough unit tests
- No integration tests yet for MCP server or full analysis pipeline

## CI/CD (GitLab)

Pipeline stages: lint → test → build-docs → pages → build → release

- **Release** only triggers on tags matching `^v\d+\.\d+\.\d+$`
- **Pages** deploys mkdocs to GitLab Pages on main branch pushes
- Uses `ghcr.io/astral-sh/uv:0.9-python3.13-bookworm-slim` image

## Configuration reference

All env vars use the `CODE_CONTEXT_` prefix:

| Variable | Default | Notes |
|----------|---------|-------|
| `CODE_CONTEXT_MODEL_ID` | `global.anthropic.claude-opus-4-6-v1` | Bedrock model |
| `CODE_CONTEXT_REGION` | `us-east-1` | AWS region |
| `CODE_CONTEXT_TEMPERATURE` | `1.0` | Must be 1.0 for adaptive thinking |
| `CODE_CONTEXT_REASONING_EFFORT` | `high` | Standard mode thinking effort |
| `CODE_CONTEXT_FULL_REASONING_EFFORT` | `max` | Full mode thinking effort (Opus 4.6 only) |
| `CODE_CONTEXT_GITNEXUS_ENABLED` | `true` | Enable GitNexus MCP for structural code intelligence |
| `CODE_CONTEXT_AGENT_MAX_TURNS` | `1000` | Standard mode max turns |
| `CODE_CONTEXT_AGENT_MAX_DURATION` | `1200` | Standard mode: 20 min default |
| `CODE_CONTEXT_FULL_MAX_TURNS` | `3000` | Full mode max agent turns |
| `CODE_CONTEXT_FULL_MAX_DURATION` | `3600` | Full mode: 60 min default |
| `CODE_CONTEXT_TEAM_EXECUTION_TIMEOUT` | `900` | Max seconds per team swarm (standard) |
| `CODE_CONTEXT_TEAM_NODE_TIMEOUT` | `900` | Max seconds per agent node in team (standard) |
| `CODE_CONTEXT_FULL_TEAM_EXECUTION_TIMEOUT` | `2400` | Max seconds per team swarm (full) |
| `CODE_CONTEXT_FULL_TEAM_NODE_TIMEOUT` | `1800` | Max seconds per agent node in team (full) |
| `CODE_CONTEXT_CONTEXT7_ENABLED` | `true` | Requires npx |
| `CODE_CONTEXT_OTEL_DISABLED` | `true` | Avoids context detachment errors |

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **code-context-agent** (2060 symbols, 4158 relationships, 113 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/code-context-agent/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/code-context-agent/context` | Codebase overview, check index freshness |
| `gitnexus://repo/code-context-agent/clusters` | All functional areas |
| `gitnexus://repo/code-context-agent/processes` | All execution flows |
| `gitnexus://repo/code-context-agent/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
