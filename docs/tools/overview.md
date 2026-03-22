# Tools Overview

code-context-agent ships with 50+ analysis tools organized into several categories. The Strands agent selects and orchestrates these tools automatically based on the codebase being analyzed.

## Tool Categories

| Category | Tools | Count | Purpose |
|----------|-------|-------|---------|
| [**Discovery**](discovery.md) | `create_file_manifest`, `repomix_orientation`, `repomix_bundle`, `repomix_bundle_with_context`, `repomix_compressed_signatures`, `repomix_split_bundle`, `repomix_json_export`, `rg_search`, `read_file_bounded`, `write_file_list`, `write_file` | 11 | File inventory, bundling, search, token-aware orientation |
| [**Search**](search.md) | `bm25_search` | 1 | BM25-ranked full-text search for concept-level queries |
| [**LSP**](lsp.md) | `lsp_start`, `lsp_document_symbols`, `lsp_references`, `lsp_definition`, `lsp_hover`, `lsp_workspace_symbols`, `lsp_diagnostics`, `lsp_shutdown` | 8 | Semantic analysis across multiple languages |
| [**AST**](ast.md) | `astgrep_scan`, `astgrep_scan_rule_pack`, `astgrep_inline_rule` | 3 | Structural pattern matching |
| [**Graph**](graph.md) | `code_graph_create`, `code_graph_ingest_lsp`, `code_graph_ingest_astgrep`, `code_graph_ingest_rg`, `code_graph_ingest_inheritance`, `code_graph_ingest_tests`, `code_graph_ingest_git`, `code_graph_ingest_clones`, `code_graph_analyze`, `code_graph_explore`, `code_graph_export`, `code_graph_save`, `code_graph_load`, `code_graph_stats` | 14 | Dependency and structural analysis (blast radius, execution flows, diff impact, confidence scoring) |
| [**Git**](git.md) | `git_hotspots`, `git_files_changed_together`, `git_blame_summary`, `git_file_history`, `git_contributors`, `git_recent_commits`, `git_diff_file` | 7 | Temporal analysis and coupling detection |
| [**Shell**](shell.md) | `shell` | 1 | Bounded, security-hardened command execution |
| [**Clone Detection**](clones.md) | `detect_clones` | 1 | Duplicate code detection via jscpd |
| **Orchestration** | `graph` | 1 | Multi-agent DAG execution (strands_tools) |
| **MCP** | `context7_resolve-library-id`, `context7_query-docs` | 2 | Library documentation lookup via context7 |

All tool inputs are validated for security. Path parameters pass through traversal prevention, glob patterns are checked for injection characters, and search patterns are validated for length and syntax. See [Security](../security/overview.md) for details.

## How Tools Are Selected

The agent follows the signal layering strategy defined in [Tenet 2](../architecture/tenets.md#2-layer-signals-read-less):

1. **Discovery first** -- File manifest and orientation establish the scope
2. **Broad signals** -- Graph creation, git hotspots, and AST scans cover the entire codebase
3. **Targeted analysis** -- LSP references, definitions, and hover for high-scoring files
4. **Bundling** -- Top-ranked files are compressed and bundled for output

The agent adapts its tool usage based on what is available. If an LSP server fails to start, it compensates with additional AST and search analysis ([Tenet 6](../architecture/tenets.md#6-fail-loud-fill-gaps)).
