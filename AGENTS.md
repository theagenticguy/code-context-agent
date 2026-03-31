# code-context-agent

AI-powered CLI tool that analyzes codebases and produces structured context
documentation for AI coding assistants.

## Architecture

Two-stage pipeline: deterministic index (21 steps, ~30-90s) → Coordinator Agent dispatches parallel Swarm teams → structured output with narrative bundles.
Hook-driven display (Rich TUI or JSON logs). No AG-UI dependency.

```
CLI (cyclopts) → index (deterministic, ~30-90s)
                    ├── 21 steps: LSP + AST-grep + git + framework detection
                    ├── code_graph.json (6K+ nodes)
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
    ├── LSP + AST-grep + git analysis (no LLM)
    ├── Framework detection (8 frameworks)
    ├── Edge confidence scoring (0.60–0.95 per source)
    ├── GraphStorage backend (NetworkX or KuzuDB)
    └── heuristic_summary.json (bridge to coordinator)

FastMCP v3 Server (code-context-agent serve)
    ├── start_analysis / check_analysis (kickoff/poll)
    ├── query_code_graph (13 graph algorithms incl. blast_radius, flows)
    ├── diff_impact / execute_cypher / list_repos
    ├── explore_code_graph (progressive disclosure)
    ├── Next-step hints in all tool responses
    └── 6 resource templates (analysis artifacts)

Multi-Repo Registry (~/.code-context/registry.json)
    ├── Lazy graph cache with 5-min TTL
    └── list_repos MCP tool

Web Visualization (code-context-agent viz)
    └── D3.js force-directed graph with controls, info panel, dark theme
```

### Key source locations

| Path | What |
|------|------|
| `src/code_context_agent/cli.py` | CLI entry point: `analyze`, `serve`, `viz` commands |
| `src/code_context_agent/config.py` | Settings via pydantic-settings, `CODE_CONTEXT_` prefix |
| `src/code_context_agent/agent/coordinator.py` | Coordinator agent factory: tools, model, heuristic summary, lean prompt |
| `src/code_context_agent/agent/factory.py` | Analysis tool collection: `get_analysis_tools()` for team inheritance |
| `src/code_context_agent/agent/runner.py` | Analysis runner with coordinator invocation + hook-based display |
| `src/code_context_agent/agent/hooks.py` | HookProviders: quality, compaction, tool efficiency, reasoning, fail-fast, team dispatch, display |
| `src/code_context_agent/tools/coordinator_tools.py` | 4 coordinator tools: `dispatch_team`, `read_team_findings`, `write_bundle`, `read_heuristic_summary` |
| `src/code_context_agent/consumer/phases.py` | 5-phase `AnalysisPhase` enum and tool-to-phase mapping |
| `src/code_context_agent/mcp/server.py` | FastMCP v3 server (MCP tools + resources) |
| `src/code_context_agent/tools/discovery.py` | ripgrep, repomix tools |
| `src/code_context_agent/tools/lsp/` | LSP client, session manager, tool wrappers |
| `src/code_context_agent/tools/graph/` | CodeGraph model, CodeAnalyzer, ProgressiveExplorer |
| `src/code_context_agent/tools/git.py` | Git history analysis tools |
| `src/code_context_agent/tools/astgrep.py` | AST-grep pattern matching tools |
| `src/code_context_agent/tools/search/` | BM25 ranked text search |
| `src/code_context_agent/tools/graph/storage.py` | GraphStorage protocol, KuzuDB backend |
| `src/code_context_agent/tools/graph/frameworks.py` | Framework detection patterns |
| `src/code_context_agent/indexer.py` | Deterministic index pipeline (no LLM) |
| `src/code_context_agent/mcp/registry.py` | Multi-repo registry with lazy graph cache |
| `src/code_context_agent/ui/` | Multi-view web visualizer (10 views, D3.js + Tailwind CSS) |
| `src/code_context_agent/templates/` | Jinja2 prompts: `coordinator.md.j2` (~35 lines), partials/, steering/. Rendering in `templates/__init__.py` |
| `src/code_context_agent/models/output.py` | AnalysisResult, Bundle, BusinessLogicItem, ArchitecturalRisk, RefactoringCandidate, CodeHealthMetrics |

### Tool categories (53+)

- **Coordinator** (4): `dispatch_team`, `read_team_findings`, `write_bundle`, `read_heuristic_summary`
- **Discovery** (12): `create_file_manifest`, `repomix_orientation`, `repomix_bundle`, `repomix_bundle_with_context`, `repomix_compressed_signatures`, `repomix_json_export`, `repomix_split_bundle`, `rg_search`, `write_file`, `write_file_list`, `read_file_bounded`
- **Search** (1): `bm25_search` (BM25 ranked text search via rank_bm25)
- **LSP** (8): `lsp_start`, `lsp_document_symbols`, `lsp_references`, `lsp_definition`, `lsp_hover`, `lsp_workspace_symbols`, `lsp_diagnostics`, `lsp_shutdown`
- **Graph** (14): `code_graph_create`, `code_graph_ingest_lsp`, `code_graph_ingest_astgrep`, `code_graph_ingest_rg`, `code_graph_ingest_inheritance`, `code_graph_ingest_tests`, `code_graph_ingest_git`, `code_graph_ingest_clones`, `code_graph_analyze` (incl. `blast_radius`, `flows`, `diff_impact`), `code_graph_explore`, `code_graph_export`, `code_graph_save/load`, `code_graph_stats`. Includes framework detection (8 frameworks) for entry point scoring and edge confidence scoring (0.60-0.95 per source).
- **Git** (7): `git_hotspots`, `git_files_changed_together`, `git_blame_summary`, `git_file_history`, `git_contributors`, `git_recent_commits`, `git_diff_file`
- **AST** (3): `astgrep_scan`, `astgrep_scan_rule_pack`, `astgrep_inline_rule`
- **Code Health** (1): `detect_clones`
- **Shell** (1): `shell`
- **Orchestration** (1): `graph` (from strands_tools, multi-agent DAG — used by team agents)
- **MCP** (via context7 + registry): `context7_resolve-library-id`, `context7_query-docs`, `list_repos`, `diff_impact`, `execute_cypher`. All MCP tool responses include contextual `next_steps` hints.

### State management

- **Code graphs**: Module-level `_graphs: dict[str, CodeGraph]` in `tools/graph/tools.py`
- **Team findings**: File-based at `.code-context/tmp/teams/{team_id}/findings.md` + `metadata.json`
- **Heuristic summary**: `.code-context/heuristic_summary.json` (bridge between indexer and coordinator)
- **Coordinator tools config**: Module-level `_output_dir`, `_repo_path`, `_tool_registry` in `tools/coordinator_tools.py`
- **LSP sessions**: Singleton `LspSessionManager` in `tools/lsp/session.py` with fallback chains
- **MCP jobs**: Module-level `_jobs` dict in `mcp/server.py` for kickoff/poll pattern
- **Registry**: `~/.code-context/registry.json` with lazy graph cache (5-min TTL) in `mcp/registry.py`
- **KuzuDB**: Optional persistent graph backend via `CODE_CONTEXT_GRAPH_BACKEND=kuzu` in `tools/graph/storage.py`
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

### LSP tools have fallback chains

Each language has an ordered list of LSP servers in `config.py`. If the primary
returns empty results, `_try_fallback_session()` in `tools/lsp/tools.py` tries
the next server. When adding a new language, add it to `Settings.lsp_servers`.

### Pydantic models use custom base classes

- `FrozenModel`: Immutable, for data transfer (output models, graph nodes/edges)
- `StrictModel`: Mutable, for internal state

Both are in `models/base.py`. Use `FrozenModel` for new data models.

## Development

### Prerequisites

- Python 3.13+ (managed via `mise`)
- Node.js 22+ (managed via `mise`)
- `uv` for Python package management
- `pnpm` for frontend package management (managed via `mise`)
- External CLIs: `rg` (ripgrep), `ast-grep`, `repomix`, `npx` (for context7)
- AWS credentials configured for Bedrock access

### Commands

| Task | Command |
|------|---------|
| Install all deps | `mise run install:all` |
| Install Python deps | `mise run install` |
| Install frontend deps | `mise run ui:install` |
| Run CLI | `uv run code-context-agent` |
| Analyze a repo | `uv run code-context-agent analyze /path/to/repo` |
| Analyze (bundles only) | `uv run code-context-agent analyze /path --bundles-only` |
| Index a repo | `uv run code-context-agent index /path/to/repo` |
| Start MCP server | `uv run code-context-agent serve` |
| Lint (Python) | `mise run lint` |
| Lint (frontend) | `mise run ui:lint` |
| Format (Python) | `mise run format` |
| Format (frontend) | `mise run ui:format` |
| Type check (Python) | `mise run typecheck` |
| Type check (frontend) | `mise run ui:typecheck` |
| Test | `mise run test` |
| All checks | `mise run check` |
| Build (frontend + package) | `mise run build` |
| Frontend dev server | `mise run ui:dev` |
| Commit | `uv run cz commit` |
| Bump + tag | `uv run cz bump` then `git push origin <tag>` |

### Git hooks (lefthook)

Hooks are enforced automatically. Do not skip them.

- **pre-commit**: ruff check+fix, ruff format, ty check, biome check (frontend), gitleaks
- **commit-msg**: conventional commit validation via commitizen
- **pre-push**: lint, format-check, typecheck, test, ui-lint, ui-typecheck, gitleaks, semgrep OWASP

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
- Tools directory has relaxed lint rules (PLR0911, PLR0912, etc.) for dispatch patterns

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
| `CODE_CONTEXT_LSP_SERVERS` | `{"py": ["ty server", "pyright-langserver --stdio"], ...}` | Ordered fallback chains |
| `CODE_CONTEXT_LSP_TIMEOUT` | `30` | LSP operation timeout seconds |
| `CODE_CONTEXT_LSP_STARTUP_TIMEOUT` | `30` | LSP server startup timeout seconds |
| `CODE_CONTEXT_LSP_MAX_FILES` | `5000` | Max files before LSP analysis is skipped |
| `CODE_CONTEXT_AGENT_MAX_TURNS` | `1000` | Standard mode max turns |
| `CODE_CONTEXT_AGENT_MAX_DURATION` | `1200` | Standard mode: 20 min default |
| `CODE_CONTEXT_FULL_MAX_TURNS` | `3000` | Full mode max agent turns |
| `CODE_CONTEXT_FULL_MAX_DURATION` | `3600` | Full mode: 60 min default |
| `CODE_CONTEXT_TEAM_EXECUTION_TIMEOUT` | `900` | Max seconds per team swarm (standard) |
| `CODE_CONTEXT_TEAM_NODE_TIMEOUT` | `900` | Max seconds per agent node in team (standard) |
| `CODE_CONTEXT_FULL_TEAM_EXECUTION_TIMEOUT` | `2400` | Max seconds per team swarm (full) |
| `CODE_CONTEXT_FULL_TEAM_NODE_TIMEOUT` | `1800` | Max seconds per agent node in team (full) |
| `CODE_CONTEXT_CONTEXT7_ENABLED` | `true` | Requires npx |
| `CODE_CONTEXT_GRAPH_BACKEND` | `networkx` | `networkx` or `kuzu` (KuzuDB persistent graph) |
| `CODE_CONTEXT_OTEL_DISABLED` | `true` | Avoids context detachment errors |
