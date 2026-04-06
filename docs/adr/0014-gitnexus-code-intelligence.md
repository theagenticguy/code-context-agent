# ADR-0014: GitNexus Code Intelligence

**Date**: 2026-04-06

**Status**: accepted (supersedes structural graph portions of [ADR-0002](0002-networkx-multi-layer-code-graph.md) and [ADR-0005](0005-lsp-fallback-chains.md))

## Context

The internal code graph system built on NetworkX ([ADR-0002](0002-networkx-multi-layer-code-graph.md)) and LSP fallback chains ([ADR-0005](0005-lsp-fallback-chains.md)) provided structural code intelligence through:

- `CodeGraph` (NetworkX `MultiDiGraph`) with 8 typed edge layers (CALLS, IMPORTS, REFERENCES, CONTAINS, INHERITS, IMPLEMENTS, TESTS, COCHANGES, SIMILAR_TO)
- `CodeAnalyzer` algorithms (PageRank, betweenness centrality, TrustRank, Leiden/Louvain community detection)
- 7 graph ingest tools (`code_graph_ingest_lsp`, `_astgrep`, `_rg`, `_inheritance`, `_tests`, `_git`, `_clones`)
- `LspSessionManager` with ordered fallback chains per language (ty -> pyright for Python, etc.)
- AST-grep rule packs for pattern matching

This infrastructure had several limitations:

- **Maintenance burden**: ~2000+ lines across `tools/graph/`, `tools/lsp/`, and `tools/astgrep.py`, with significant complexity in LSP lifecycle management, session fallback logic, and graph serialization compatibility across NetworkX versions
- **Limited language support**: LSP fallback chains were only configured for Python (ty, pyright) and TypeScript. Adding Go, Rust, or Java required installing and configuring additional LSP servers
- **In-memory only**: The NetworkX graph lived in process memory, limiting analysis of large codebases and preventing reuse across CLI invocations
- **Ingestion latency**: Building the graph required sequential LSP startup, AST-grep rule evaluation, and ripgrep-based reference resolution — adding 30-60s to each analysis run

## Decision

Delegate structural code intelligence to **GitNexus**, an external CLI tool that provides Tree-sitter-based parsing, symbol clustering, and execution flow tracing. GitNexus replaces the internal graph, LSP, and AST-grep subsystems.

Integration points:

- **Indexer phase** (`src/code_context_agent/indexer.py`): The `_run_gitnexus_analyze()` step runs `gitnexus analyze` as a subprocess during the deterministic index pipeline. It produces a `.gitnexus/` directory with a knowledge graph (stored in `.gitnexus/meta.json` and associated data files). The heuristic summary generator reads `.gitnexus/meta.json` for community count, process count, symbol count, and edge count.
- **MCP tool loading** (`src/code_context_agent/agent/factory.py`): The `_create_gitnexus_provider()` function creates a `strands.tools.mcp.MCPClient` wrapping `npx gitnexus mcp` as a stdio MCP server. Tools are prefixed with `gitnexus_` (e.g., `gitnexus_query`, `gitnexus_context`, `gitnexus_impact`, `gitnexus_detect_changes`, `gitnexus_cypher`, `gitnexus_list_repos`). The MCPClient is appended to the analysis tools list and managed by the strands Agent lifecycle.
- **Coordinator integration**: The coordinator template (`templates/coordinator.md.j2`) references GitNexus community and process metrics from the heuristic summary to plan teams. Team agents use `gitnexus_query` for concept search, `gitnexus_context` for 360-degree symbol views, and `gitnexus_impact` for blast radius analysis.
- **Configuration**: Controlled by `CODE_CONTEXT_GITNEXUS_ENABLED` (default `true`). Requires `npx` (Node.js) at runtime for both the indexer step and the MCP server.
- **Heuristic summary bridge**: `_get_gitnexus_stats()` in `indexer.py` reads `.gitnexus/meta.json` for stats and optionally queries `gitnexus cypher` for top community names with symbol counts and cohesion scores. These metrics feed into `heuristic_summary.json` under the `gitnexus` section.

## Consequences

**Positive:**

- Removed ~2000 lines of internal graph/LSP/AST-grep code, significantly reducing maintenance surface
- Multi-language support via Tree-sitter: GitNexus parses Python, TypeScript, JavaScript, Rust, Go, Java, and others without per-language LSP configuration
- Community detection and execution flow tracing are handled by GitNexus's clustering algorithms, replacing the internal Leiden/Louvain community detection and TrustRank analysis
- Persistent graph data in `.gitnexus/` survives across CLI invocations; re-analysis only rebuilds what changed
- MCP-based integration is a clean boundary: the agent communicates with GitNexus through well-defined tool calls, not in-memory API coupling
- GitNexus provides Cypher query support for ad-hoc graph exploration, which is more flexible than the fixed algorithm set in `CodeAnalyzer`

**Negative:**

- External dependency on `gitnexus` CLI (requires Node.js and `npx`), adding a system-level prerequisite
- Graph data is not directly accessible in Python — all queries go through MCP tool calls, adding latency compared to in-memory NetworkX operations
- The `.gitnexus/` directory is managed by an external tool; its format and schema may change across GitNexus versions without notice
- If GitNexus is unavailable or fails during indexing, the coordinator loses structural intelligence (community-aware team planning, blast radius analysis) and falls back to text-search-only analysis

**Neutral:**

- ADR-0002 (NetworkX graph) and ADR-0005 (LSP fallback chains) remain `accepted` in status since the ADR records describe decisions that were valid at the time; this ADR supersedes the structural graph portions but the historical decisions stand
- The MCP server lifecycle is managed by strands `MCPClient`, which starts the server on first use and stops it when the agent completes — no manual lifecycle management needed
- GitNexus index freshness is the user's responsibility; the CLAUDE.md instructions include a PostToolUse hook that auto-re-indexes after commits
