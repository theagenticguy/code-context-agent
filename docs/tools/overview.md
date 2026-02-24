# Tools Overview

code-context-agent ships with 40+ analysis tools organized into six categories. The Strands agent selects and orchestrates these tools automatically based on the codebase being analyzed.

## Tool Categories

| Category | Tools | Count | Purpose |
|----------|-------|-------|---------|
| [**Discovery**](discovery.md) | `create_file_manifest`, `repomix_orientation`, `repomix_bundle`, `repomix_compressed_signatures`, `repomix_split_bundle`, `repomix_json_export` | 6 | File inventory, bundling, token-aware orientation |
| [**Search**](discovery.md) | `rg_search`, `read_file_bounded` | 2 | Text search and bounded file reading |
| [**LSP**](lsp.md) | `lsp_start`, `lsp_document_symbols`, `lsp_references`, `lsp_definition`, `lsp_hover`, `lsp_workspace_symbols`, `lsp_diagnostics` | 7 | Semantic analysis across multiple languages |
| [**AST**](ast.md) | `astgrep_scan`, `astgrep_scan_rule_pack`, `astgrep_inline_rule` | 3 | Structural pattern matching |
| [**Graph**](graph.md) | `code_graph_create`, `code_graph_analyze` (6 modes), `code_graph_explore`, `code_graph_export` | 12 | Dependency and structural analysis |
| [**Git**](git.md) | `git_hotspots`, `git_files_changed_together`, `git_blame_summary`, `git_file_history`, `git_contributors`, `git_recent_commits`, `git_diff_file` | 7 | Temporal analysis and coupling detection |
| **Shell** | `shell` | 1 | Bounded command execution |

## How Tools Are Selected

The agent follows the signal layering strategy defined in [Tenet 2](../architecture/tenets.md#2-layer-signals-read-less):

1. **Discovery first** --- File manifest and orientation establish the scope
2. **Broad signals** --- Graph creation, git hotspots, and AST scans cover the entire codebase
3. **Targeted analysis** --- LSP references, definitions, and hover for high-scoring files
4. **Bundling** --- Top-ranked files are compressed and bundled for output

The agent adapts its tool usage based on what's available. If an LSP server fails to start, it compensates with additional AST and search analysis ([Tenet 6](../architecture/tenets.md#6-fail-loud-fill-gaps)).
