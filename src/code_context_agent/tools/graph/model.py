"""Core data structures for code graph analysis.

This module defines the fundamental types for representing code as a graph:
- NodeType/EdgeType enums for classification
- CodeNode/CodeEdge Pydantic models for graph elements
- CodeGraph class wrapping NetworkX MultiDiGraph
"""

from enum import Enum
from typing import Any

import networkx as nx
from pydantic import Field

from ...models.base import FrozenModel


class NodeType(Enum):
    """Types of nodes in the code graph."""

    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    MODULE = "module"
    PATTERN_MATCH = "pattern_match"  # AST-grep match


class EdgeType(Enum):
    """Types of relationships between code elements."""

    CALLS = "calls"  # Function/method call
    IMPORTS = "imports"  # Module import
    REFERENCES = "references"  # Symbol reference
    CONTAINS = "contains"  # Containment (file→function, class→method)
    INHERITS = "inherits"  # Class/type inheritance
    IMPLEMENTS = "implements"  # Interface implementation
    TESTS = "tests"  # Test → production code coverage
    COCHANGES = "cochanges"  # Files that frequently change together (git history)
    SIMILAR_TO = "similar_to"  # Cloned/duplicated code blocks


# LSP SymbolKind to NodeType mapping
# https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#symbolKind
LSP_SYMBOL_KIND_MAP: dict[int, NodeType] = {
    1: NodeType.FILE,  # File
    2: NodeType.MODULE,  # Module
    5: NodeType.CLASS,  # Class
    6: NodeType.METHOD,  # Method
    9: NodeType.FUNCTION,  # Constructor (treated as method)
    12: NodeType.FUNCTION,  # Function
    13: NodeType.VARIABLE,  # Variable
    14: NodeType.VARIABLE,  # Constant
    23: NodeType.CLASS,  # Struct
    # Default to VARIABLE for unknown kinds
}


def lsp_kind_to_node_type(kind: int) -> NodeType:
    """Convert LSP SymbolKind to NodeType."""
    return LSP_SYMBOL_KIND_MAP.get(kind, NodeType.VARIABLE)


class CodeNode(FrozenModel):
    """A node in the code graph representing a code element.

    Attributes:
        id: Unique identifier (typically "file_path:symbol_name" or "file_path:line")
        name: Human-readable display name
        node_type: Classification of the code element
        file_path: Absolute path to the source file
        line_start: Starting line number (0-indexed)
        line_end: Ending line number (0-indexed)
        metadata: Additional properties (docstring, visibility, rule_id, etc.)
    """

    id: str
    name: str
    node_type: NodeType
    file_path: str
    line_start: int
    line_end: int
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = self.model_dump()
        result["node_type"] = self.node_type.value
        return result


class CodeEdge(FrozenModel):
    """An edge in the code graph representing a relationship.

    Attributes:
        source: Source node ID
        target: Target node ID
        edge_type: Classification of the relationship
        weight: Edge weight for algorithms (default 1.0)
        metadata: Additional properties (line where relationship occurs, etc.)
    """

    source: str
    target: str
    edge_type: EdgeType
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = self.model_dump()
        result["edge_type"] = self.edge_type.value
        return result


class CodeGraph:
    """Multi-layer code graph supporting multiple relationship types.

    Wraps a NetworkX MultiDiGraph to support:
    - Multiple edge types between the same node pair
    - Node/edge attributes for metadata
    - Filtered views for specific relationship types
    """

    def __init__(self) -> None:
        """Initialize an empty code graph."""
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()

    def __len__(self) -> int:
        """Return the number of nodes in the graph."""
        return self._graph.number_of_nodes()

    @property
    def node_count(self) -> int:
        """Return the number of nodes."""
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        """Return the number of edges."""
        return self._graph.number_of_edges()

    def add_node(self, node: CodeNode) -> None:
        """Add a node to the graph.

        Args:
            node: The CodeNode to add
        """
        self._graph.add_node(
            node.id,
            name=node.name,
            node_type=node.node_type.value,
            file_path=node.file_path,
            line_start=node.line_start,
            line_end=node.line_end,
            **node.metadata,
        )

    def add_edge(self, edge: CodeEdge) -> None:
        """Add an edge to the graph.

        Args:
            edge: The CodeEdge to add
        """
        self._graph.add_edge(
            edge.source,
            edge.target,
            key=edge.edge_type.value,
            edge_type=edge.edge_type.value,
            weight=edge.weight,
            **edge.metadata,
        )

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists in the graph."""
        return self._graph.has_node(node_id)

    def has_edge(self, source: str, target: str, edge_type: EdgeType | None = None) -> bool:
        """Check if an edge exists in the graph.

        Args:
            source: Source node ID
            target: Target node ID
            edge_type: Optional edge type to check for specifically
        """
        if edge_type is None:
            return self._graph.has_edge(source, target)
        return self._graph.has_edge(source, target, key=edge_type.value)

    def get_node_data(self, node_id: str) -> dict[str, Any] | None:
        """Get the data associated with a node.

        Args:
            node_id: The node ID to look up

        Returns:
            Dictionary of node attributes or None if not found
        """
        if not self._graph.has_node(node_id):
            return None
        return dict(self._graph.nodes[node_id])

    def get_nodes_by_type(self, node_type: NodeType) -> list[str]:
        """Get all node IDs of a specific type.

        Args:
            node_type: The type to filter by

        Returns:
            List of node IDs matching the type
        """
        return [n for n, d in self._graph.nodes(data=True) if d.get("node_type") == node_type.value]

    def get_edges_by_type(self, edge_type: EdgeType) -> list[tuple[str, str, dict[str, Any]]]:
        """Get all edges of a specific type.

        Args:
            edge_type: The type to filter by

        Returns:
            List of (source, target, data) tuples
        """
        return [(u, v, d) for u, v, k, d in self._graph.edges(keys=True, data=True) if k == edge_type.value]

    def get_view(self, edge_types: list[EdgeType] | None = None) -> nx.DiGraph:
        """Get a filtered view of the graph for analysis algorithms.

        Creates a simple DiGraph (not Multi) with only the specified edge types.
        Multiple edges between the same nodes are aggregated by summing weights.

        Args:
            edge_types: List of edge types to include (None = all types)

        Returns:
            A NetworkX DiGraph suitable for analysis algorithms
        """
        view = nx.DiGraph()

        # Copy all nodes with their attributes
        view.add_nodes_from(self._graph.nodes(data=True))

        # Filter and aggregate edges
        for u, v, k, d in self._graph.edges(keys=True, data=True):
            if edge_types is None or EdgeType(k) in edge_types:
                if view.has_edge(u, v):
                    # Aggregate weights
                    view[u][v]["weight"] += d.get("weight", 1.0)
                else:
                    view.add_edge(u, v, weight=d.get("weight", 1.0), types=[k])

        return view

    def nodes(self, data: bool = False) -> Any:
        """Return nodes, optionally with data.

        Args:
            data: If True, return (node_id, data) tuples

        Returns:
            Node view from underlying NetworkX graph
        """
        return self._graph.nodes(data=data)

    def edges(self, data: bool = False) -> Any:
        """Return edges, optionally with data.

        Args:
            data: If True, return (source, target, data) tuples

        Returns:
            Edge view from underlying NetworkX graph
        """
        return self._graph.edges(data=data)

    def to_node_link_data(self) -> dict[str, Any]:
        """Export graph as node-link JSON format.

        Returns:
            Dictionary suitable for JSON serialization
        """
        return nx.node_link_data(self._graph)

    @classmethod
    def from_node_link_data(cls, data: dict[str, Any]) -> "CodeGraph":
        """Create a CodeGraph from node-link JSON format.

        Handles both old NetworkX format ("links" key) and new 3.6+
        format ("edges" key) for backward compatibility with saved graphs.

        Args:
            data: Dictionary from node_link_data or JSON

        Returns:
            New CodeGraph instance
        """
        graph = cls()
        # Handle both old ("links") and new ("edges") format
        if "links" in data and "edges" not in data:
            graph._graph = nx.node_link_graph(data, edges="links")
        else:
            graph._graph = nx.node_link_graph(data)
        return graph

    def describe(self) -> dict[str, Any]:
        """Get a quick summary of the graph.

        Returns:
            Dictionary with node count, edge count, type distributions, and density.
        """
        node_types: dict[str, int] = {}
        for _, data in self._graph.nodes(data=True):
            nt = data.get("node_type", "unknown")
            node_types[nt] = node_types.get(nt, 0) + 1

        edge_types: dict[str, int] = {}
        for _, _, k, _ in self._graph.edges(keys=True, data=True):
            edge_types[k] = edge_types.get(k, 0) + 1

        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "node_types": node_types,
            "edge_types": edge_types,
            "density": nx.density(self._graph),
        }
