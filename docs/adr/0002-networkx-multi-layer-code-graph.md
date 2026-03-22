# ADR-0002: NetworkX Multi-Layer Code Graph

**Date**: 2025-02-01

**Status**: accepted

## Context

The agent needs to represent code relationships across multiple signal types to perform structural analysis. Required relationship types include:

- `CALLS` (function/method invocations)
- `IMPORTS` (module imports)
- `REFERENCES` (symbol references from LSP)
- `CONTAINS` (file-to-symbol containment)
- `INHERITS` / `IMPLEMENTS` (type hierarchy)
- `TESTS` (test-to-production coverage)
- `COCHANGES` (files that frequently change together from git history)
- `SIMILAR_TO` (cloned/duplicated code blocks)

The graph must support multiple edges between the same node pair (a function can both call and reference another), typed filtering for algorithm-specific views, and standard graph algorithms (PageRank, betweenness centrality, community detection).

Alternatives considered:

- **Neo4j / purpose-built graph DB**: Richer query language (Cypher) but requires external service, complicates deployment for a CLI tool
- **igraph**: Faster for large graphs but less Pythonic API and weaker multi-edge support
- **Custom adjacency lists**: Lightweight but no algorithm library

## Decision

Use `nx.MultiDiGraph` from NetworkX, wrapped in a `CodeGraph` class at `src/code_context_agent/tools/graph/model.py`.

Key design elements:

- **Typed nodes** (`CodeNode` with `NodeType` enum: FILE, CLASS, FUNCTION, METHOD, VARIABLE, MODULE, PATTERN_MATCH) stored as Pydantic `FrozenModel` instances
- **Typed edges** (`CodeEdge` with `EdgeType` enum) using the edge type as the MultiDiGraph key, allowing multiple relationship types per node pair
- **Filtered views** via `CodeGraph.get_view(edge_types)` that produce a simple `nx.DiGraph` suitable for algorithms that do not support multigraphs
- **Analysis algorithms** in `CodeAnalyzer` (`src/code_context_agent/tools/graph/analysis.py`): PageRank, betweenness centrality, TrustRank (personalized PageRank from entry points), Leiden/Louvain community detection, triangle detection, coupling measurement, dependency chain traversal
- **Progressive exploration** via `ProgressiveExplorer` (`src/code_context_agent/tools/graph/disclosure.py`) for interactive drill-down
- **Serialization** via `nx.node_link_data()` / `nx.node_link_graph()` to JSON, persisted as `.code-context/code_graph.json`

Graph ingestion happens through 7 dedicated ingest tools (`code_graph_ingest_lsp`, `_astgrep`, `_rg`, `_inheritance`, `_tests`, `_git`, `_clones`) that each add typed edges from their respective signal sources.

## Consequences

**Positive:**

- Rich algorithm library out of the box: PageRank, betweenness, Louvain/Leiden, shortest paths, clique detection all work directly on the graph
- `MultiDiGraph` naturally models the multi-layer nature of code relationships (same node pair can have `CALLS`, `REFERENCES`, and `COCHANGES` edges simultaneously)
- JSON serialization enables persistence and MCP server consumption without graph DB infrastructure
- `networkx[extra]` dependency brings `scipy` and community detection backends

**Negative:**

- In-memory only; large monorepos (100K+ nodes) may hit memory limits
- `get_view()` creates a copy of the graph for each algorithm call (not a zero-copy view)
- JSON serialization format changed between NetworkX 3.5 (`links` key) and 3.6+ (`edges` key), requiring compatibility handling in `from_node_link_data()`

**Neutral:**

- Graph state is module-level (`_graphs: dict[str, CodeGraph]` in `tools/graph/tools.py`), not per-agent; this is acceptable for single-agent CLI usage
- The `CodeGraph` wrapper deliberately does not expose the full NetworkX API, providing a controlled surface area
