# ADR-0009: KuzuDB Persistent Graph Backend

**Date**: 2026-03-22

**Status**: accepted

## Context

The code graph (nodes for modules, classes, functions; edges for calls, imports, inheritance) is built in-memory using NetworkX during each analysis session. This has two limitations:

1. **No persistence**: The graph is lost when the session ends. Re-analyzing a large repo rebuilds the entire graph from scratch, repeating LSP queries and AST parsing.
2. **No native query language**: NetworkX requires imperative Python for graph traversal. Cypher queries would enable the AI agent (and MCP clients) to ask ad-hoc structural questions like "find all classes that inherit from BaseModel and are referenced by more than 3 modules."

Alternatives considered:

- **Neo4j**: Industry-standard graph database but requires a running server process, Java runtime, and network configuration. Too heavy for a CLI tool.
- **SQLite with recursive CTEs**: Could model graphs relationally, but graph traversal queries become unwieldy and slow compared to native graph storage.
- **Pickle/JSON serialization of NetworkX**: Simple persistence but no query language, no incremental updates, and large file sizes for big graphs.

## Decision

Add KuzuDB as an optional persistent graph backend behind a `GraphStorage` protocol. NetworkX remains the default in-memory backend.

Key design choices:

- **`GraphStorage` protocol** defines the interface (`add_node`, `add_edge`, `query`, `to_networkx`, etc.) so backends are swappable
- **NetworkX remains default** — zero-config, no extra dependencies, works exactly as before
- **KuzuDB provides**: embedded graph database (no server), Cypher query support, on-disk persistence, and cross-session graph continuity
- **Bidirectional conversion**: `to_networkx()` and `from_networkx()` methods allow KuzuDB-stored graphs to use NetworkX algorithms (PageRank, community detection, etc.)
- **Opt-in via configuration**: `CODE_CONTEXT_GRAPH_BACKEND=kuzu` activates the KuzuDB backend
- **ty type checker excluded** for `storage.py` due to imprecise kuzu stubs that produce false positives

## Consequences

**Positive:**

- Graphs persist across sessions — re-opening a previously analyzed repo loads the graph instantly instead of rebuilding
- Cypher queries enable powerful ad-hoc structural analysis without writing Python traversal code
- `execute_cypher` MCP tool exposes Cypher to external AI assistants
- Embedded database (no server process) keeps the CLI tool self-contained
- NetworkX algorithm compatibility preserved via conversion methods

**Negative:**

- Adds `kuzu` as an optional dependency (only installed when the backend is selected)
- Conversion to/from NetworkX for algorithms has overhead on very large graphs
- KuzuDB schema must be kept in sync with the `CodeGraph` Pydantic models; schema migrations are manual
- ty type checker exclusion for `storage.py` reduces type safety coverage for that module

**Neutral:**

- Default behavior is unchanged; existing users see no difference unless they opt in
- Graph database files are stored alongside analysis output, managed by the existing output directory structure
