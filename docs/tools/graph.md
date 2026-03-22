# Graph Analysis

The graph tools use [NetworkX](https://networkx.org/) to build and analyze dependency graphs, providing quantitative metrics that drive file ranking ([Tenet 1](../architecture/tenets.md#1-measure-dont-guess)).

## Tools

### `code_graph_create`

Builds a dependency graph from the codebase using import/reference relationships. Nodes are files; edges represent dependencies (imports, references, co-changes).

### `code_graph_analyze`

Runs analysis algorithms on the graph. Supports fifteen analysis modes:

#### Hotspots (Betweenness Centrality)

Identifies bridge/bottleneck files that sit on many shortest paths between other files. High betweenness centrality indicates files that, if changed, have widespread impact.

#### Foundations (PageRank)

Identifies foundational modules using the PageRank algorithm. Files with high PageRank are depended upon by many other important files.

#### Trust (TrustRank)

Variant of PageRank that propagates trust from known-good seed files. Useful for identifying reliable, well-tested modules.

#### Modules (Louvain/Leiden)

Detects community structure using Louvain or Leiden community detection algorithms. Groups files into modules based on their connectivity patterns, revealing the codebase's actual module boundaries (which often differ from directory structure).

#### Triangles

Finds tightly coupled triads -- sets of three files where each depends on the other two. Triangles indicate strong coupling that may represent either cohesive modules or problematic circular dependencies.

#### Coupling

Analyzes the coupling between graph communities/modules. Identifies which modules have the most cross-dependencies.

#### Unused Symbols

Identifies symbols (functions, classes) that exist in the graph but have no incoming references. These are candidates for dead code removal.

#### Refactoring

Analyzes the graph for refactoring opportunities: duplicate code clusters (from clone detection), high-coupling modules, and files that bridge too many communities.

#### Blast Radius

Computes the impact of changing a specific node. BFS outward through reverse edges (callers, importers, references) with exponential decay: each hop halves the impact score. Edge confidence is factored into the decay, so low-confidence edges attenuate propagation. Returns total affected nodes, a risk score (sum of all impacts), a depth histogram, and ranked affected nodes.

```
Impact formula: 1 / (2^distance) * confidence_product
```

Requires `node_a` parameter. Use for: pre-change risk assessment, identifying high-impact refactoring targets.

#### Execution Flows

Traces execution paths from entry points through CALLS edges using DFS. Identifies named flows from entry points to leaves (or depth cutoff), deduplicates prefix paths, and scores flows by length and degree. Returns up to `max_flows` results sorted by score. Use for: understanding request handling paths, documenting execution architecture.

#### Diff Impact

Maps git diff changed lines to graph nodes and computes aggregate blast radius. For each changed file+line range, finds overlapping graph nodes by line overlap, runs blast radius on each, merges results, and suggests test files via TESTS edges. Returns directly changed nodes, aggregate risk score, affected nodes, and suggested tests.

Requires `node_a` parameter containing a JSON array of changed files:

```json
[{"file_path": "src/foo.py", "lines": [10, 11, 12]}]
```

Use for: PR review impact assessment, CI test selection.

### `code_graph_explore`

Interactive exploration of the graph. Allows querying neighbors, paths, and subgraphs for specific files or modules.

### `code_graph_export`

Exports the graph to `code_graph.json` for persistence and downstream consumption. The exported format includes node metrics, edges, and community assignments.

### `code_graph_save`

Persists the complete code graph to disk for reuse in future sessions. Saves all nodes with metadata (file paths, line numbers, categories) and all edges with types (calls, references, imports, inherits). Saved graphs can be reloaded with `code_graph_load`, avoiding the need to re-run LSP and ast-grep tools.

### `code_graph_load`

Loads a previously saved code graph from disk. Restores all nodes, edges, and metadata, making the graph immediately available for analysis and exploration. Loading replaces any existing graph with the same ID.

### `code_graph_stats`

Returns summary statistics about a code graph: total node and edge counts broken down by type. Useful for verifying that graph ingestion worked correctly (e.g., checking that LSP produced function/class nodes, ast-grep produced pattern_match nodes).

### `code_graph_ingest_lsp`

Ingests LSP tool results (symbols, references, definitions) into the graph. Creates nodes for functions, classes, and methods, and edges for call/reference/import relationships.

### `code_graph_ingest_astgrep`

Ingests ast-grep scan results into the graph. Creates `pattern_match` nodes and links them to the files where patterns were found.

### `code_graph_ingest_rg`

Ingests ripgrep search results into the graph. Creates text-match edges between files based on shared patterns.

### `code_graph_ingest_inheritance`

Ingests class inheritance relationships into the graph. Creates `INHERITS` edges between class nodes.

### `code_graph_ingest_tests`

Ingests test-production file relationships into the graph. Creates `TESTS` edges linking test files to the production files they cover.

### `code_graph_ingest_clones`

Ingests clone detection results into the graph. Creates `CLONE` edges between files that share duplicate code blocks, with metadata about the duplicated line ranges.

### `code_graph_ingest_git`

Adds git history data to the code graph. Supports three result types:

- **`hotspots`** -- from `git_hotspots`. Creates or updates FILE nodes with churn metadata.
- **`cochanges`** -- from `git_files_changed_together`. Creates COCHANGES edges between co-changing files, filtered by a configurable `min_percentage` threshold.
- **`contributors`** -- from `git_contributors` or `git_blame_summary`. Attaches ownership metadata to FILE nodes.

## Edge Confidence Scoring

Every `CodeEdge` carries a `confidence` field (0.0--1.0) indicating how reliable the data source is. Edges from LSP definitions have confidence 1.0 (precise semantic data), while ripgrep text-match edges may carry lower confidence. Confidence affects:

- **Blast radius propagation** -- low-confidence edges attenuate impact scores at each hop
- **View aggregation** -- when multiple edges between the same node pair are aggregated, the max confidence is kept
- **Ranking quality** -- high-confidence edges contribute more to centrality and PageRank calculations

## Framework Detection

The `frameworks` module detects framework-specific patterns (Next.js pages, FastAPI routes, Django views, Express handlers, etc.) from file paths and applies scoring boosts to entry points. Detected frameworks include:

| Framework | Detection Pattern | Entry Point Boost |
|-----------|------------------|-------------------|
| Next.js | `pages/**/*.tsx`, `app/**/page.tsx` | 3.0x |
| FastAPI | `@(app\|router).(get\|post\|...)` | 3.0x |
| Django | `**/views.py`, `**/urls.py` | 2.5--3.0x |
| Express | `app.(get\|post\|use)` | 3.0x |
| Flask | `@app.route`, `@blueprint.route` | 3.0x |
| CLI | `**/cli.py`, `**/__main__.py` | 2.5--3.0x |
| pytest | `**/test_*.py`, `**/conftest.py` | 1.5x |

Framework detection runs automatically during `find_entry_points()` when framework patterns are provided.

## How Graph Metrics Drive Ranking

Files are scored using a weighted combination of graph metrics:

```
score = w1 * betweenness_centrality
      + w2 * pagerank
      + w3 * git_churn_normalized
      + w4 * coupling_score
      + w5 * ast_pattern_hits
```

The agent adjusts weights based on available signals. If git history is unavailable, graph metrics receive higher weight. If LSP fails, AST pattern hits compensate.
