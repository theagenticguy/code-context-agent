# Graph Storage Backends

The graph storage layer is abstracted behind a `GraphStorage` protocol, allowing the code graph to be backed by different storage engines.

## Backends

### NetworkXStorage (default)

In-memory storage wrapping the existing `CodeGraph` class. All data lives in a NetworkX `MultiDiGraph` and is lost when the process exits unless explicitly saved to JSON.

- Zero external dependencies (NetworkX is already required)
- Fast for graphs under ~10K nodes
- Saved/loaded via `code_graph_save`/`code_graph_load` (JSON format)

### KuzuStorage (persistent)

Persistent storage backed by [KuzuDB](https://kuzudb.com/), an embedded graph database. Data is stored on disk in a KuzuDB database directory and persists across sessions without explicit save operations.

- Supports Cypher queries via `execute_cypher`
- Automatic schema creation (CodeNode and CodeEdge tables)
- Placeholder node creation when adding edges with missing endpoints
- Converts to NetworkX for algorithm compatibility (`to_code_graph()`)

## KuzuDB Schema

```cypher
CREATE NODE TABLE CodeNode(
    id STRING,
    name STRING,
    node_type STRING,
    file_path STRING,
    line_start INT64,
    line_end INT64,
    metadata STRING,
    PRIMARY KEY(id)
)

CREATE REL TABLE CodeEdge(
    FROM CodeNode TO CodeNode,
    edge_type STRING,
    weight DOUBLE,
    confidence DOUBLE,
    metadata STRING
)
```

## Cypher Queries

When using KuzuDB, the `execute_cypher` MCP tool allows custom read-only Cypher queries against the graph:

```cypher
-- Find all functions
MATCH (n:CodeNode) WHERE n.node_type = 'function'
RETURN n.id, n.name LIMIT 10

-- Find call relationships
MATCH (a:CodeNode)-[e:CodeEdge]->(b:CodeNode)
WHERE e.edge_type = 'calls'
RETURN a.id, b.id LIMIT 20

-- Count nodes by type
MATCH (n:CodeNode) RETURN n.node_type, count(n)

-- Find high-confidence edges
MATCH (a)-[e:CodeEdge]->(b)
WHERE e.confidence > 0.8
RETURN a.id, b.id, e.edge_type, e.confidence
```

Write operations (CREATE, DELETE, SET, MERGE, DROP, ALTER) are blocked for safety.

## Configuration

Set the graph backend via environment variable:

```bash
# Use KuzuDB (persistent)
export CODE_CONTEXT_GRAPH_BACKEND=kuzu

# Use NetworkX (default, in-memory)
export CODE_CONTEXT_GRAPH_BACKEND=networkx
```

When using KuzuDB, the database is stored at `.code-context/graph.kuzu` inside the repository.

## GraphStorage Protocol

Custom backends can be created by implementing the `GraphStorage` protocol:

```python
class GraphStorage(Protocol):
    def add_node(self, node: CodeNode) -> None: ...
    def add_edge(self, edge: CodeEdge) -> None: ...
    def has_node(self, node_id: str) -> bool: ...
    def get_node_data(self, node_id: str) -> dict[str, Any] | None: ...
    def get_nodes_by_type(self, node_type: NodeType) -> list[str]: ...
    def get_edges_by_type(self, edge_type: EdgeType) -> list[tuple[str, str, dict[str, Any]]]: ...
    def node_count(self) -> int: ...
    def edge_count(self) -> int: ...
    def to_node_link_data(self) -> dict[str, Any]: ...
    def describe(self) -> dict[str, Any]: ...
```
