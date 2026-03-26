# code-context-agent

AI-powered CLI tool that analyzes codebases and produces structured context
documentation for AI coding assistants. v8.0.1.

## Architecture

Three-stage pipeline: deterministic index → Strands Swarm (4 specialist agents) → structured output.
Hook-driven display (Rich TUI or JSON logs). No AG-UI dependency.

```
CLI (cyclopts) → index (deterministic, ~30s)
                    ├── LSP + AST-grep + git + framework detection
                    └── code_graph.json (6K+ nodes)

              → analyze (Swarm, ~5-10 min)
                    ├── structure_analyst → history_analyst → code_reader → synthesizer
                    ├── Pre-loaded index graph shared via _graphs["main"]
                    ├── HookProvider-driven display (TUI or JSON logs)
                    └── AnalysisResult (structured output from synthesizer)

Deterministic Indexer (code-context-agent index)
    ├── LSP + AST-grep + git analysis (no LLM)
    ├── Framework detection (8 frameworks)
    ├── Edge confidence scoring (0.60–0.95 per source)
    └── GraphStorage backend (NetworkX or KuzuDB)

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
| `src/code_context_agent/agent/factory.py` | Single-agent creation: tools, model, hooks, context7 MCP |
| `src/code_context_agent/agent/swarm.py` | Swarm factory: 4-node specialist pipeline with graph preloading |
| `src/code_context_agent/agent/runner.py` | Analysis runner with Swarm execution + hook-based display |
| `src/code_context_agent/agent/analysts.py` | Specialist prompts (Agents-as-Tools + Swarm handoff variants) |
| `src/code_context_agent/agent/hooks.py` | HookProviders: reasoning checkpoints, display, JSON logging |
| `src/code_context_agent/agent/prompts.py` | Jinja2 template rendering |
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
| `src/code_context_agent/viz/index.html` | D3.js interactive graph visualization |
| `src/code_context_agent/templates/` | Jinja2 system prompt (system.md.j2 + partials/ + steering/) |
| `src/code_context_agent/models/output.py` | AnalysisResult, BusinessLogicItem, ArchitecturalRisk |

### Tool categories (50+)

- **Discovery** (9): `create_file_manifest`, `repomix_*`, `rg_search`, `read_file_bounded`, `write_file_list`
- **Search** (1): `bm25_search` (BM25 ranked text search via rank_bm25)
- **LSP** (8): `lsp_start`, `lsp_document_symbols`, `lsp_references`, `lsp_definition`, `lsp_hover`, `lsp_workspace_symbols`, `lsp_diagnostics`, `lsp_shutdown`
- **Graph** (14): `code_graph_create`, `code_graph_ingest_*`, `code_graph_analyze` (incl. `blast_radius`, `flows`, `diff_impact`), `code_graph_explore`, `code_graph_export`, `code_graph_save/load`, `code_graph_stats`. Includes framework detection (8 frameworks) for entry point scoring and edge confidence scoring (0.60-0.95 per source).
- **Git** (7): `git_hotspots`, `git_files_changed_together`, `git_blame_summary`, `git_file_history`, `git_contributors`, `git_recent_commits`, `git_diff_file`
- **AST** (3): `astgrep_scan`, `astgrep_scan_rule_pack`, `astgrep_inline_rule`
- **Shell** (1): `shell`
- **MCP** (via context7 + registry): `context7_resolve-library-id`, `context7_query-docs`, `list_repos`, `diff_impact`, `execute_cypher`. All MCP tool responses include contextual `next_steps` hints.
- **Orchestration** (1): `graph` (from strands_tools, multi-agent DAG)

### State management

- **Code graphs**: Module-level `_graphs: dict[str, CodeGraph]` in `tools/graph/tools.py`
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
- `uv` for package management
- External CLIs: `rg` (ripgrep), `ast-grep`, `repomix`, `npx` (for context7)
- AWS credentials configured for Bedrock access

### Commands

| Task | Command |
|------|---------|
| Install all deps | `uv sync --all-groups` |
| Run CLI | `uv run code-context-agent` |
| Analyze a repo | `uv run code-context-agent analyze /path/to/repo` |
| Index a repo | `uv run code-context-agent index /path/to/repo` |
| Start MCP server | `uv run code-context-agent serve` |
| Lint | `uvx ruff check src/` |
| Format | `uvx ruff format src/` |
| Type check | `uvx ty check src/` |
| Test | `uv run pytest` |
| All checks | `mise run check` |
| Commit | `uv run cz commit` |
| Bump + tag | `uv run cz bump` then `git push origin <tag>` |

### Git hooks (lefthook)

Hooks are enforced automatically. Do not skip them.

- **pre-commit**: ruff check+fix, ruff format, ty check, gitleaks
- **commit-msg**: conventional commit validation via commitizen
- **pre-push**: lint, format-check, typecheck, test (362 tests), gitleaks, semgrep OWASP

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
| `CODE_CONTEXT_LSP_SERVERS` | `{"py": ["ty server", "pyright-langserver --stdio"], ...}` | Ordered fallback chains |
| `CODE_CONTEXT_AGENT_MAX_TURNS` | `1000` | |
| `CODE_CONTEXT_AGENT_MAX_DURATION` | `1200` | 20 min default |
| `CODE_CONTEXT_CONTEXT7_ENABLED` | `true` | Requires npx |
| `CODE_CONTEXT_GRAPH_BACKEND` | `networkx` | `networkx` or `kuzu` (KuzuDB persistent graph) |
| `CODE_CONTEXT_OTEL_DISABLED` | `true` | Avoids context detachment errors |
