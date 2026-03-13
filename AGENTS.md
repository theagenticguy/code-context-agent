# code-context-agent

AI-powered CLI tool that analyzes codebases and produces structured context
documentation for AI coding assistants. v7.0.0.

## Architecture

Single Strands Agent (Claude Opus 4.6 on Bedrock) with 40+ tools, AG-UI
event streaming, and Pydantic structured output (`AnalysisResult`).

```
CLI (cyclopts) → run_analysis() → Strands Agent (Opus 4.6)
                                      ├── 40+ @tool functions
                                      ├── context7 MCP (library docs)
                                      ├── AG-UI event stream → Rich TUI
                                      └── AnalysisResult (structured output)

FastMCP v3 Server (code-context-agent serve)
    ├── start_analysis / check_analysis (kickoff/poll)
    ├── query_code_graph (10 graph algorithms)
    ├── explore_code_graph (progressive disclosure)
    └── 6 resource templates (analysis artifacts)
```

### Key source locations

| Path | What |
|------|------|
| `src/code_context_agent/cli.py` | CLI entry point: `analyze`, `serve`, `viz` commands |
| `src/code_context_agent/config.py` | Settings via pydantic-settings, `CODE_CONTEXT_` prefix |
| `src/code_context_agent/agent/factory.py` | Agent creation: tools, model, hooks, context7 MCP |
| `src/code_context_agent/agent/runner.py` | Analysis runner with AG-UI event streaming |
| `src/code_context_agent/agent/prompts.py` | Jinja2 template rendering |
| `src/code_context_agent/mcp/server.py` | FastMCP v3 server (MCP tools + resources) |
| `src/code_context_agent/tools/discovery.py` | ripgrep, repomix tools |
| `src/code_context_agent/tools/lsp/` | LSP client, session manager, tool wrappers |
| `src/code_context_agent/tools/graph/` | CodeGraph model, CodeAnalyzer, ProgressiveExplorer |
| `src/code_context_agent/tools/git.py` | Git history analysis tools |
| `src/code_context_agent/tools/astgrep.py` | AST-grep pattern matching tools |
| `src/code_context_agent/templates/` | Jinja2 system prompt (system.md.j2 + partials/ + steering/) |
| `src/code_context_agent/models/output.py` | AnalysisResult, BusinessLogicItem, ArchitecturalRisk |

### Tool categories (40+)

- **Discovery** (9): `create_file_manifest`, `repomix_*`, `rg_search`, `read_file_bounded`, `write_file_list`
- **LSP** (8): `lsp_start`, `lsp_document_symbols`, `lsp_references`, `lsp_definition`, `lsp_hover`, `lsp_workspace_symbols`, `lsp_diagnostics`, `lsp_shutdown`
- **Graph** (12): `code_graph_create`, `code_graph_ingest_*`, `code_graph_analyze`, `code_graph_explore`, `code_graph_export`, `code_graph_save/load`, `code_graph_stats`
- **Git** (7): `git_hotspots`, `git_files_changed_together`, `git_blame_summary`, `git_file_history`, `git_contributors`, `git_recent_commits`, `git_diff_file`
- **AST** (3): `astgrep_scan`, `astgrep_scan_rule_pack`, `astgrep_inline_rule`
- **Shell** (1): `shell`
- **MCP** (via context7): `context7_resolve-library-id`, `context7_query-docs`
- **Orchestration** (1): `graph` (from strands_tools, multi-agent DAG)

### State management

- **Code graphs**: Module-level `_graphs: dict[str, CodeGraph]` in `tools/graph/tools.py`
- **LSP sessions**: Singleton `LspSessionManager` in `tools/lsp/session.py` with fallback chains
- **MCP jobs**: Module-level `_jobs` dict in `mcp/server.py` for kickoff/poll pattern
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
- **pre-push**: lint, format-check, typecheck, test (93 tests), gitleaks, semgrep OWASP

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
| `CODE_CONTEXT_OTEL_DISABLED` | `true` | Avoids context detachment errors |
