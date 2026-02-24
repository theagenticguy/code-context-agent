# Graph Analysis

The graph tools use [NetworkX](https://networkx.org/) to build and analyze dependency graphs, providing quantitative metrics that drive file ranking ([Tenet 1](../architecture/tenets.md#1-measure-dont-guess)).

## Tools

### `code_graph_create`

Builds a dependency graph from the codebase using import/reference relationships. Nodes are files; edges represent dependencies (imports, references, co-changes).

### `code_graph_analyze`

Runs analysis algorithms on the graph. Supports six analysis modes:

#### Hotspots (Betweenness Centrality)

Identifies bridge/bottleneck files that sit on many shortest paths between other files. High betweenness centrality indicates files that, if changed, have widespread impact.

#### Foundations (PageRank)

Identifies foundational modules using the PageRank algorithm. Files with high PageRank are depended upon by many other important files.

#### Trust (TrustRank)

Variant of PageRank that propagates trust from known-good seed files. Useful for identifying reliable, well-tested modules.

#### Modules (Louvain/Leiden)

Detects community structure using Louvain or Leiden community detection algorithms. Groups files into modules based on their connectivity patterns, revealing the codebase's actual module boundaries (which often differ from directory structure).

#### Triangles

Finds tightly coupled triads --- sets of three files where each depends on the other two. Triangles indicate strong coupling that may represent either cohesive modules or problematic circular dependencies.

#### Coupling

Analyzes the coupling between graph communities/modules. Identifies which modules have the most cross-dependencies.

### `code_graph_explore`

Interactive exploration of the graph. Allows querying neighbors, paths, and subgraphs for specific files or modules.

### `code_graph_export`

Exports the graph to `code_graph.json` for persistence and downstream consumption. The exported format includes node metrics, edges, and community assignments.

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
