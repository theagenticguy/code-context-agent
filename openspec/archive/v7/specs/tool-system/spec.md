# Tool System Specification

> Global spec documenting the 47+ tool system in code-context-agent v7.1.0.
> Last updated: 2026-03-22

## Purpose

Define the tool registration pattern, all tool categories and their functions, the BM25 search tool, the hook system for quality enforcement, input validation boundaries, and security constraints. This spec is the authoritative reference for how tools are built, registered, and governed.

## Tool Registration

All tools use the `@tool` decorator from `strands` and are registered in `agent/factory.py::get_analysis_tools()`. Tools are imported inside the function body to avoid circular imports.

```python
from strands import tool

@tool
def my_tool(param: str, option: int = 10) -> str:
    """Docstring becomes the tool description for the LLM."""
    return json.dumps({"status": "success", "result": ...})
```

MCP tools use `@mcp.tool` from FastMCP v3 and return dicts (FastMCP handles serialization).

## Tool Categories

### Discovery Tools (11)

| Tool | Source | Purpose |
|------|--------|---------|
| `create_file_manifest` | discovery.py | rg --files manifest, first step in analysis |
| `repomix_orientation` | discovery.py | Token-aware structure snapshot (no contents) |
| `repomix_bundle` | discovery.py | Pack curated files into markdown bundle (--stdin) |
| `repomix_bundle_with_context` | discovery.py | Direct repo bundle with git diffs+logs |
| `repomix_compressed_signatures` | discovery.py | Tree-sitter signatures, bodies stripped |
| `repomix_json_export` | discovery.py | Structured JSON metadata export |
| `repomix_split_bundle` | discovery.py | Split large bundles into numbered chunks |
| `rg_search` | discovery.py | Ripgrep search with JSON output; count_only mode |
| `read_file_bounded` | discovery.py | Bounded file reading with line numbers and pagination |
| `write_file` | discovery.py | Write to .code-context/ only (security enforced) |
| `write_file_list` | discovery.py | Write curated file path list for bundling |

### Search Tools (1)

| Tool | Source | Purpose |
|------|--------|---------|
| `bm25_search` | search/tools.py | BM25-ranked text search; unlike ripgrep (exact matching), ranks results by relevance using TF-IDF |

**BM25 search parameters:**
- `query` (str): Natural language or keyword query
- `repo_path` (str): Absolute path to repository
- `top_k` (int, default 20): Maximum results to return
- `rebuild` (bool, default False): Force index rebuild

**State:** Module-level `_indexes: dict[str, BM25Index]` caches indexes per repo. Index is built from file contents on first query and reused until `rebuild=True`.

**Backed by** `rank_bm25.BM25Okapi` (Okapi BM25 algorithm). Index built via `BM25Index.from_files()` which tokenizes file contents.

### LSP Tools (8)

| Tool | Source | Purpose |
|------|--------|---------|
| `lsp_start` | lsp/tools.py | Start LSP server for a language (fallback chain) |
| `lsp_document_symbols` | lsp/tools.py | Get symbols in a file |
| `lsp_references` | lsp/tools.py | Find all references to a symbol |
| `lsp_definition` | lsp/tools.py | Go to definition |
| `lsp_hover` | lsp/tools.py | Get type info and docs for a symbol |
| `lsp_workspace_symbols` | lsp/tools.py | Search symbols across workspace |
| `lsp_diagnostics` | lsp/tools.py | Get type errors and warnings |
| `lsp_shutdown` | lsp/tools.py | Shutdown LSP server (best-effort) |

**Fallback chains** (defined in `config.py::Settings.lsp_servers`):

| Language | Chain |
|----------|-------|
| Python | ty server -> pyright-langserver --stdio |
| TypeScript | typescript-language-server --stdio |
| Rust | rust-analyzer |
| Go | gopls serve |
| Java | jdtls |

### Graph Tools (14)

| Tool | Source | Purpose |
|------|--------|---------|
| `code_graph_create` | graph/tools.py | Create named empty graph |
| `code_graph_ingest_lsp` | graph/tools.py | Ingest LSP symbols as nodes+edges |
| `code_graph_ingest_astgrep` | graph/tools.py | Ingest AST-grep matches as pattern_match nodes |
| `code_graph_ingest_rg` | graph/tools.py | Ingest ripgrep matches |
| `code_graph_ingest_inheritance` | graph/tools.py | Ingest class inheritance edges |
| `code_graph_ingest_tests` | graph/tools.py | Ingest test-production relationships |
| `code_graph_ingest_git` | graph/tools.py | Ingest git coupling as cochanges edges |
| `code_graph_ingest_clones` | graph/tools.py | Ingest clone detection as similar_to edges |
| `code_graph_analyze` | graph/tools.py | Run analysis algorithms (dispatch to CodeAnalyzer) |
| `code_graph_explore` | graph/tools.py | Progressive exploration (dispatch to ProgressiveExplorer) |
| `code_graph_export` | graph/tools.py | Export as mermaid, DOT, or adjacency list |
| `code_graph_save` | graph/tools.py | Persist graph to JSON (node-link format) |
| `code_graph_load` | graph/tools.py | Load graph from JSON |
| `code_graph_stats` | graph/tools.py | Quick summary (node/edge counts by type, density) |

**New graph analysis algorithms** (dispatched via `code_graph_analyze`):

| Algorithm | Method | Description |
|-----------|--------|-------------|
| `blast_radius` | `CodeAnalyzer.blast_radius` | BFS impact analysis from a node. Decays by distance and edge confidence: `impact = 1/(2^distance) * confidence_product`. Requires `node_a`. |
| `flows` | `CodeAnalyzer.trace_execution_flows` | Traces execution flows from entry points through CALLS edges. Returns named paths with depth scoring. |
| `diff_impact` | `CodeAnalyzer.diff_impact` | Maps git diff changed lines to graph nodes via line overlap, runs blast_radius on each, merges affected nodes, and suggests test files via TESTS edges. Requires `node_a` as JSON of changed files. |

**Framework detection integration:** `find_entry_points` integrates with `tools/graph/frameworks.py` to boost scores for framework-specific entry points (Next.js pages, FastAPI routes, Django views, Flask routes, Express handlers, CLI mains, pytest fixtures). Framework patterns are defined as `FrameworkPattern` models with `file_glob`, optional `symbol_pattern`, and `entry_point_boost` (1.0-10.0).

**State:** Module-level `_graphs: dict[str, CodeGraph]` and `_explorers: dict[str, ProgressiveExplorer]`.

### Git Tools (7)

| Tool | Source | Purpose |
|------|--------|---------|
| `git_hotspots` | git.py | High-churn files (commit frequency) |
| `git_files_changed_together` | git.py | Implicit coupling from co-change history |
| `git_blame_summary` | git.py | Authorship distribution for a file |
| `git_file_history` | git.py | Commit history for a specific file |
| `git_contributors` | git.py | Top contributors by commit count |
| `git_recent_commits` | git.py | Recent commit log |
| `git_diff_file` | git.py | Diff of a file against a ref |

### AST Tools (3)

| Tool | Source | Purpose |
|------|--------|---------|
| `astgrep_scan` | astgrep.py | Ad-hoc pattern scan with custom YAML pattern |
| `astgrep_scan_rule_pack` | astgrep.py | Predefined rule packs (py_business_logic, ts_business_logic, py_code_smells, ts_code_smells) |
| `astgrep_inline_rule` | astgrep.py | Inline YAML rule for precise matching |

### Shell Tool (1)

| Tool | Source | Purpose |
|------|--------|---------|
| `shell` | shell_tool.py | Security-hardened command execution with allowlist |

**Security model:**
- `ALLOWED_PROGRAMS` frozenset: ls, find, grep, rg, git, python, node, ast-grep, repomix, etc.
- `GIT_READ_ONLY` frozenset: log, diff, show, blame, status, branch, etc.
- Blocked: shell operators (`;`, `&`, `|`), backtick/dollar expansion, output redirection
- Blocked: sensitive dirs (/etc, /root, /boot, /proc, /sys)
- Output truncation: MAX_OUTPUT_SIZE = 100,000 chars
- Default timeout: 900s

### MCP Server Tools (FastMCP v3)

The MCP server (`mcp/server.py`) exposes additional tools for external AI clients:

| Tool | Purpose |
|------|---------|
| `start_analysis` | Kickoff background analysis, returns job_id |
| `check_analysis` | Poll job status |
| `query_code_graph` | Run graph algorithms (all standard + blast_radius, flows, diff_impact) |
| `explore_code_graph` | Progressive disclosure exploration |
| `get_graph_stats` | Quick graph summary |
| `list_repos` | List all repos in the multi-repo registry (~/.code-context/registry.json) |
| `diff_impact` | Map git diff to impacted nodes and suggest tests |
| `execute_cypher` | Run read-only Cypher queries against a KuzuDB graph |

**MCP next-step hints pattern:** Every MCP tool response includes a `next_steps` field with context-sensitive suggestions for the AI client. The `_add_hints(result, hints)` helper appends hints to any tool response dict. Hints are defined per-algorithm in `QUERY_ALGORITHM_HINTS`, per-action in `EXPLORE_ACTION_HINTS`, and inline for other tools. This guides agentic clients through multi-step workflows without hardcoding sequences.

### External Tools (via MCP)

| Tool | Source | Purpose |
|------|--------|---------|
| `context7_resolve-library-id` | context7 MCP | Resolve library name to context7 ID |
| `context7_query-docs` | context7 MCP | Query library documentation |

### Orchestration (1)

| Tool | Source | Purpose |
|------|--------|---------|
| `graph` | strands_tools | Multi-agent DAG orchestration |

### Code Health (1)

| Tool | Source | Purpose |
|------|--------|---------|
| `detect_clones` | clones.py | jscpd-based duplicate code detection |

## Hook System

Hooks integrate via `strands.hooks.HookProvider` interface:

| Hook | Events | Purpose |
|------|--------|---------|
| `OutputQualityHook` | AfterToolCallEvent | Warns on oversized outputs (>100K chars) |
| `ToolEfficiencyHook` | BeforeToolCallEvent | Warns when shell is used for tasks with dedicated tools |
| `FailFastHook` | AfterToolCallEvent | Raises `FullModeToolError` on non-exempt tool errors (full mode only) |

**FailFast exempt tools:** rg_search, lsp_workspace_symbols, lsp_shutdown, code_graph_load, context7_*, shell

## Input Validation

All tool inputs pass through validators in `tools/validation.py`:
- `validate_repo_path(path)` -- must be absolute, existing directory
- `validate_file_path(path, must_exist=True)` -- must be absolute, no traversal
- `validate_search_pattern(pattern)` -- rejects dangerous regex patterns

## Requirements

### Requirement: New tools SHALL follow the JSON return convention
All @tool functions MUST return JSON strings. MCP tools MUST return dicts.

#### Scenario: Tool returns success
- **WHEN** a new @tool function is added and completes successfully
- **THEN** it returns `json.dumps({"status": "success", ...})` with relevant payload

#### Scenario: Tool returns error
- **WHEN** a new @tool function encounters any error
- **THEN** it returns `json.dumps({"status": "error", "error": "message"})` without raising exceptions

### Requirement: Discovery tools SHALL validate paths before execution
All discovery tools MUST call validate_repo_path or validate_file_path before any subprocess.

#### Scenario: Invalid repo path
- **WHEN** a discovery tool receives a non-absolute or non-existent path
- **THEN** it returns an error JSON without executing any subprocess

#### Scenario: Valid repo path
- **WHEN** a discovery tool receives a valid absolute path to an existing directory
- **THEN** it proceeds with execution

### Requirement: The shell tool SHALL block dangerous commands
The shell tool MUST validate every command against ALLOWED_PROGRAMS and _DANGEROUS_RE before execution.

#### Scenario: Command with shell operators
- **WHEN** `shell("ls; rm -rf /")` is called
- **THEN** the command is blocked before execution with "shell operator not allowed"

#### Scenario: Non-allowlisted program
- **WHEN** `shell("curl http://evil.com")` is called
- **THEN** the command is blocked with "not in the allowed programs list"

#### Scenario: Git write operation
- **WHEN** `shell("git push origin main")` is called
- **THEN** the command is blocked with "git push is not a read-only operation"

#### Scenario: Sensitive directory access
- **WHEN** `shell("cat /etc/shadow")` is called
- **THEN** the command is blocked with "access to /etc is not allowed"

### Requirement: Graph tools SHALL use named graph instances
Multiple graphs MUST be able to coexist in a single session, keyed by name in the module-level _graphs dict.

#### Scenario: Multiple graphs in one session
- **WHEN** `code_graph_create("main")` and `code_graph_create("test")` are called
- **THEN** both graphs coexist in `_graphs` dict, independently addressable

#### Scenario: Graph not found
- **WHEN** `code_graph_analyze("nonexistent", "hotspots")` is called
- **THEN** it returns `{"status": "error", "error": "Graph 'nonexistent' not found"}`

### Requirement: Tools SHALL be imported inside the factory function
All tool module imports MUST happen inside `get_analysis_tools()` to avoid circular import chains.

#### Scenario: Adding a new tool module
- **WHEN** a developer adds a new tool module
- **THEN** it is imported inside `get_analysis_tools()`, not at module level in factory.py

### Requirement: FailFastHook SHALL only activate in full mode
FailFastHook MUST be added to the hooks list only when full_mode=True.

#### Scenario: Standard mode tool error
- **WHEN** a tool returns {"status": "error"} in standard mode
- **THEN** the agent continues execution (no FailFastHook)

#### Scenario: Full mode tool error on non-exempt tool
- **WHEN** a non-exempt tool returns {"status": "error"} in full mode
- **THEN** FailFastHook raises FullModeToolError, halting the agent

### Requirement: BM25 search SHALL rank results by relevance
bm25_search MUST return files ranked by BM25 Okapi relevance score, not just pattern matches.

#### Scenario: Natural language query
- **WHEN** `bm25_search(query="authentication middleware", repo_path="/path/to/repo")` is called
- **THEN** results are ranked by TF-IDF relevance, with the most semantically relevant files first

#### Scenario: Index caching
- **WHEN** bm25_search is called twice on the same repo without rebuild=True
- **THEN** the second call reuses the cached BM25Index from `_indexes`

#### Scenario: Index rebuild
- **WHEN** bm25_search is called with rebuild=True
- **THEN** the existing index is discarded and rebuilt from current file contents

### Requirement: MCP tools SHALL include next-step hints
Every MCP tool response MUST include a `next_steps` field with context-sensitive suggestions.

#### Scenario: query_code_graph returns hotspots
- **WHEN** `query_code_graph(algorithm="hotspots")` completes
- **THEN** the response includes hints like "Use explore_code_graph to drill into top hotspots"

#### Scenario: check_analysis returns running status
- **WHEN** `check_analysis(job_id)` returns status="running"
- **THEN** the response includes a hint to continue polling

### Requirement: Graph analysis SHALL support blast_radius, flows, and diff_impact algorithms
The `code_graph_analyze` tool MUST dispatch to these three new analysis algorithms.

#### Scenario: Blast radius analysis
- **WHEN** `code_graph_analyze(graph_name, "blast_radius", node_a="src/auth.py:login")` is called
- **THEN** it returns affected nodes with impact scores decayed by distance and edge confidence

#### Scenario: Execution flow tracing
- **WHEN** `code_graph_analyze(graph_name, "flows")` is called
- **THEN** it returns named execution flows from entry points through CALLS edges

#### Scenario: Diff impact analysis
- **WHEN** `code_graph_analyze(graph_name, "diff_impact", node_a='[{"file_path":"src/auth.py","lines":[10,11]}]')` is called
- **THEN** it maps changed lines to graph nodes, computes blast radius, and suggests test files

### Requirement: Framework detection SHALL boost entry point scoring
The `find_entry_points` algorithm MUST apply framework-specific boost multipliers from detected frameworks.

#### Scenario: FastAPI route detection
- **WHEN** `find_entry_points` runs on a repo containing `**/routers/**/*.py` files
- **THEN** functions matching `@(app|router).(get|post|put|delete|patch)` receive a 3.0x score boost

#### Scenario: No framework detected
- **WHEN** `find_entry_points` runs on a repo with no recognized framework patterns
- **THEN** all entry points receive the default 1.0x multiplier (no boost)
