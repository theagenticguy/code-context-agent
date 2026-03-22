"""Graph storage backends for code graph persistence.

Provides a ``GraphStorage`` protocol and two implementations:

- ``NetworkXStorage`` — in-memory, wraps the existing ``CodeGraph`` (default)
- ``KuzuStorage`` — persistent, backed by KuzuDB on disk with Cypher query support
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import kuzu
import networkx as nx

from code_context_agent.tools.graph.model import CodeEdge, CodeGraph, CodeNode, EdgeType, NodeType


@runtime_checkable
class GraphStorage(Protocol):
    """Protocol for graph storage backends."""

    def add_node(self, node: CodeNode) -> None:
        """Add a node to the graph."""
        ...

    def add_edge(self, edge: CodeEdge) -> None:
        """Add an edge to the graph."""
        ...

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists."""
        ...

    def get_node_data(self, node_id: str) -> dict[str, Any] | None:
        """Get node attribute data."""
        ...

    def get_nodes_by_type(self, node_type: NodeType) -> list[str]:
        """Get all node IDs of a specific type."""
        ...

    def get_edges_by_type(self, edge_type: EdgeType) -> list[tuple[str, str, dict[str, Any]]]:
        """Get all edges of a specific type."""
        ...

    def node_count(self) -> int:
        """Return the number of nodes."""
        ...

    def edge_count(self) -> int:
        """Return the number of edges."""
        ...

    def to_node_link_data(self) -> dict[str, Any]:
        """Export to node-link JSON format."""
        ...

    def describe(self) -> dict[str, Any]:
        """Get a summary of the graph."""
        ...


class NetworkXStorage:
    """NetworkX-backed graph storage (default, in-memory)."""

    def __init__(self, graph: CodeGraph | None = None) -> None:
        """Initialize with an optional existing CodeGraph."""
        self._graph = graph or CodeGraph()

    def add_node(self, node: CodeNode) -> None:
        """Add a node to the graph."""
        self._graph.add_node(node)

    def add_edge(self, edge: CodeEdge) -> None:
        """Add an edge to the graph."""
        self._graph.add_edge(edge)

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists."""
        return self._graph.has_node(node_id)

    def get_node_data(self, node_id: str) -> dict[str, Any] | None:
        """Get node attribute data."""
        return self._graph.get_node_data(node_id)

    def get_nodes_by_type(self, node_type: NodeType) -> list[str]:
        """Get all node IDs of a specific type."""
        return self._graph.get_nodes_by_type(node_type)

    def get_edges_by_type(self, edge_type: EdgeType) -> list[tuple[str, str, dict[str, Any]]]:
        """Get all edges of a specific type."""
        return self._graph.get_edges_by_type(edge_type)

    def node_count(self) -> int:
        """Return the number of nodes."""
        return self._graph.node_count

    def edge_count(self) -> int:
        """Return the number of edges."""
        return self._graph.edge_count

    def to_node_link_data(self) -> dict[str, Any]:
        """Export to node-link JSON format."""
        return self._graph.to_node_link_data()

    def describe(self) -> dict[str, Any]:
        """Get a summary of the graph."""
        return self._graph.describe()

    @property
    def graph(self) -> CodeGraph:
        """Return the underlying CodeGraph."""
        return self._graph


class KuzuStorage:
    """KuzuDB-backed persistent graph storage.

    Stores the code graph in a KuzuDB database directory for persistence
    across sessions. Supports Cypher queries for advanced graph analysis.
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialize KuzuDB storage at the given path."""
        self._db_path = Path(db_path)
        # Ensure parent directory exists; KuzuDB creates the db_path itself
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self._db_path))
        self._conn = kuzu.Connection(self._db)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create node and edge tables if they don't exist."""
        try:
            self._conn.execute(
                "CREATE NODE TABLE IF NOT EXISTS CodeNode("
                "id STRING, name STRING, node_type STRING, file_path STRING, "
                "line_start INT64, line_end INT64, metadata STRING, "
                "PRIMARY KEY(id))",
            )
            self._conn.execute(
                "CREATE REL TABLE IF NOT EXISTS CodeEdge("
                "FROM CodeNode TO CodeNode, "
                "edge_type STRING, weight DOUBLE, confidence DOUBLE, metadata STRING)",
            )
        except kuzu.RuntimeError:
            pass  # Tables already exist

    def add_node(self, node: CodeNode) -> None:
        """Add or update a node in the database."""
        meta_json = json.dumps(node.metadata) if node.metadata else "{}"
        self._conn.execute(
            "MERGE (n:CodeNode {id: $id}) "
            "SET n.name = $name, n.node_type = $node_type, n.file_path = $file_path, "
            "n.line_start = $line_start, n.line_end = $line_end, n.metadata = $metadata",
            parameters={
                "id": node.id,
                "name": node.name,
                "node_type": node.node_type.value,
                "file_path": node.file_path,
                "line_start": node.line_start,
                "line_end": node.line_end,
                "metadata": meta_json,
            },
        )

    def add_edge(self, edge: CodeEdge) -> None:
        """Add an edge, auto-creating placeholder nodes if needed."""
        meta_json = json.dumps(edge.metadata) if edge.metadata else "{}"
        # Ensure both nodes exist first
        for nid in (edge.source, edge.target):
            if not self.has_node(nid):
                self._conn.execute(
                    "CREATE (n:CodeNode {id: $id, name: $id, node_type: 'unknown', "
                    "file_path: '', line_start: 0, line_end: 0, metadata: '{}'})",
                    parameters={"id": nid},
                )
        self._conn.execute(
            "MATCH (a:CodeNode), (b:CodeNode) WHERE a.id = $src AND b.id = $tgt "
            "CREATE (a)-[:CodeEdge {edge_type: $etype, weight: $weight, confidence: $conf, metadata: $meta}]->(b)",
            parameters={
                "src": edge.source,
                "tgt": edge.target,
                "etype": edge.edge_type.value,
                "weight": edge.weight,
                "conf": edge.confidence,
                "meta": meta_json,
            },
        )

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists in the database."""
        result = self._conn.execute(
            "MATCH (n:CodeNode) WHERE n.id = $id RETURN count(n)",
            parameters={"id": node_id},
        )
        while result.has_next():
            row = result.get_next()
            return row[0] > 0
        return False

    def get_node_data(self, node_id: str) -> dict[str, Any] | None:
        """Get node attributes by ID."""
        result = self._conn.execute(
            "MATCH (n:CodeNode) WHERE n.id = $id "
            "RETURN n.id, n.name, n.node_type, n.file_path, n.line_start, n.line_end",
            parameters={"id": node_id},
        )
        while result.has_next():
            row = result.get_next()
            return {
                "name": row[1],
                "node_type": row[2],
                "file_path": row[3],
                "line_start": row[4],
                "line_end": row[5],
            }
        return None

    def get_nodes_by_type(self, node_type: NodeType) -> list[str]:
        """Get all node IDs matching a specific type."""
        result = self._conn.execute(
            "MATCH (n:CodeNode) WHERE n.node_type = $ntype RETURN n.id",
            parameters={"ntype": node_type.value},
        )
        nodes = []
        while result.has_next():
            nodes.append(result.get_next()[0])
        return nodes

    def get_edges_by_type(self, edge_type: EdgeType) -> list[tuple[str, str, dict[str, Any]]]:
        """Get all edges matching a specific type."""
        result = self._conn.execute(
            "MATCH (a:CodeNode)-[e:CodeEdge]->(b:CodeNode) WHERE e.edge_type = $etype "
            "RETURN a.id, b.id, e.weight, e.confidence, e.metadata",
            parameters={"etype": edge_type.value},
        )
        edges = []
        while result.has_next():
            row = result.get_next()
            meta = json.loads(row[4]) if row[4] else {}
            edges.append((row[0], row[1], {"weight": row[2], "confidence": row[3], **meta}))
        return edges

    def node_count(self) -> int:
        """Return the total number of nodes."""
        result = self._conn.execute("MATCH (n:CodeNode) RETURN count(n)")
        while result.has_next():
            return result.get_next()[0]
        return 0

    def edge_count(self) -> int:
        """Return the total number of edges."""
        result = self._conn.execute("MATCH ()-[e:CodeEdge]->() RETURN count(e)")
        while result.has_next():
            return result.get_next()[0]
        return 0

    def execute_cypher(self, query: str) -> list[list[Any]]:
        """Execute a read-only Cypher query and return results.

        Args:
            query: A Cypher query string. Write operations are blocked.

        Returns:
            List of result rows.

        Raises:
            ValueError: If the query contains write operations.
        """
        query_upper = query.strip().upper()
        if any(kw in query_upper for kw in ("CREATE", "DELETE", "SET", "MERGE", "DROP", "ALTER")):
            msg = "Write operations are not allowed via execute_cypher"
            raise ValueError(msg)
        result = self._conn.execute(query)
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        return rows

    def to_node_link_data(self) -> dict[str, Any]:
        """Export to NetworkX-compatible node-link format."""
        graph = self._to_networkx()
        return nx.node_link_data(graph)

    def describe(self) -> dict[str, Any]:
        """Get a summary of the graph."""
        nc = self.node_count()
        ec = self.edge_count()
        node_types: dict[str, int] = {}
        result = self._conn.execute("MATCH (n:CodeNode) RETURN n.node_type, count(n)")
        while result.has_next():
            row = result.get_next()
            node_types[row[0]] = row[1]
        edge_types: dict[str, int] = {}
        result = self._conn.execute("MATCH ()-[e:CodeEdge]->() RETURN e.edge_type, count(e)")
        while result.has_next():
            row = result.get_next()
            edge_types[row[0]] = row[1]
        return {
            "node_count": nc,
            "edge_count": ec,
            "node_types": node_types,
            "edge_types": edge_types,
            "backend": "kuzu",
            "db_path": str(self._db_path),
        }

    def _to_networkx(self) -> nx.MultiDiGraph:
        """Convert to NetworkX graph for algorithm compatibility."""
        g = nx.MultiDiGraph()
        result = self._conn.execute(
            "MATCH (n:CodeNode) RETURN n.id, n.name, n.node_type, n.file_path, n.line_start, n.line_end, n.metadata",
        )
        while result.has_next():
            row = result.get_next()
            meta = json.loads(row[6]) if row[6] else {}
            g.add_node(
                row[0],
                name=row[1],
                node_type=row[2],
                file_path=row[3],
                line_start=row[4],
                line_end=row[5],
                **meta,
            )
        result = self._conn.execute(
            "MATCH (a:CodeNode)-[e:CodeEdge]->(b:CodeNode) "
            "RETURN a.id, b.id, e.edge_type, e.weight, e.confidence, e.metadata",
        )
        while result.has_next():
            row = result.get_next()
            meta = json.loads(row[5]) if row[5] else {}
            g.add_edge(
                row[0],
                row[1],
                key=row[2],
                edge_type=row[2],
                weight=row[3],
                confidence=row[4],
                **meta,
            )
        return g

    def to_code_graph(self) -> CodeGraph:
        """Convert to a CodeGraph for algorithm compatibility."""
        nxg = self._to_networkx()
        graph = CodeGraph()
        graph._graph = nxg
        return graph
