"""Tests for code graph model."""

from code_context_agent.tools.graph.model import (
    CodeEdge,
    CodeGraph,
    CodeNode,
    EdgeType,
    NodeType,
    lsp_kind_to_node_type,
)


class TestNodeType:
    """Tests for NodeType enum."""

    def test_node_types_exist(self) -> None:
        """Test that expected node types exist."""
        assert NodeType.FILE.value == "file"
        assert NodeType.CLASS.value == "class"
        assert NodeType.FUNCTION.value == "function"
        assert NodeType.METHOD.value == "method"
        assert NodeType.MODULE.value == "module"


class TestEdgeType:
    """Tests for EdgeType enum."""

    def test_edge_types_exist(self) -> None:
        """Test that expected edge types exist."""
        assert EdgeType.CALLS.value == "calls"
        assert EdgeType.IMPORTS.value == "imports"
        assert EdgeType.REFERENCES.value == "references"
        assert EdgeType.CONTAINS.value == "contains"
        assert EdgeType.INHERITS.value == "inherits"
        assert EdgeType.IMPLEMENTS.value == "implements"
        assert EdgeType.TESTS.value == "tests"
        assert EdgeType.COCHANGES.value == "cochanges"


class TestLspKindMapping:
    """Tests for LSP SymbolKind to NodeType mapping."""

    def test_class_mapping(self) -> None:
        """Test that LSP class kind maps to CLASS."""
        assert lsp_kind_to_node_type(5) == NodeType.CLASS

    def test_function_mapping(self) -> None:
        """Test that LSP function kind maps to FUNCTION."""
        assert lsp_kind_to_node_type(12) == NodeType.FUNCTION

    def test_method_mapping(self) -> None:
        """Test that LSP method kind maps to METHOD."""
        assert lsp_kind_to_node_type(6) == NodeType.METHOD

    def test_unknown_mapping(self) -> None:
        """Test that unknown kinds map to VARIABLE."""
        assert lsp_kind_to_node_type(999) == NodeType.VARIABLE


class TestCodeNode:
    """Tests for CodeNode dataclass."""

    def test_create_node(self) -> None:
        """Test creating a CodeNode."""
        node = CodeNode(
            id="src/main.py:main",
            name="main",
            node_type=NodeType.FUNCTION,
            file_path="/repo/src/main.py",
            line_start=10,
            line_end=25,
        )
        assert node.id == "src/main.py:main"
        assert node.name == "main"
        assert node.node_type == NodeType.FUNCTION
        assert node.line_start == 10  # noqa: PLR2004

    def test_node_to_dict(self) -> None:
        """Test converting node to dictionary."""
        node = CodeNode(
            id="test:node",
            name="test",
            node_type=NodeType.CLASS,
            file_path="/test.py",
            line_start=1,
            line_end=10,
            metadata={"doc": "test doc"},
        )
        result = node.to_dict()
        assert result["id"] == "test:node"
        assert result["node_type"] == "class"
        assert result["metadata"]["doc"] == "test doc"


class TestCodeEdge:
    """Tests for CodeEdge dataclass."""

    def test_create_edge(self) -> None:
        """Test creating a CodeEdge."""
        edge = CodeEdge(
            source="a:foo",
            target="b:bar",
            edge_type=EdgeType.CALLS,
            weight=2.0,
        )
        assert edge.source == "a:foo"
        assert edge.target == "b:bar"
        assert edge.edge_type == EdgeType.CALLS
        assert edge.weight == 2.0  # noqa: PLR2004

    def test_edge_to_dict(self) -> None:
        """Test converting edge to dictionary."""
        edge = CodeEdge(
            source="a",
            target="b",
            edge_type=EdgeType.IMPORTS,
        )
        result = edge.to_dict()
        assert result["source"] == "a"
        assert result["edge_type"] == "imports"


class TestCodeEdgeConfidence:
    """Tests for CodeEdge confidence field."""

    def test_code_edge_confidence_default(self) -> None:
        """Test that confidence defaults to 1.0."""
        edge = CodeEdge(source="a", target="b", edge_type=EdgeType.CALLS)
        assert edge.confidence == 1.0

    def test_code_edge_confidence_custom(self) -> None:
        """Test that an explicit confidence value is preserved."""
        edge = CodeEdge(source="a", target="b", edge_type=EdgeType.CALLS, confidence=0.75)
        assert edge.confidence == 0.75  # noqa: PLR2004

    def test_code_edge_confidence_roundtrip(self) -> None:
        """Test that to_dict includes confidence and from_node_link_data preserves it."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(id="a", name="a", node_type=NodeType.FUNCTION, file_path="/a.py", line_start=1, line_end=5),
        )
        graph.add_node(
            CodeNode(id="b", name="b", node_type=NodeType.FUNCTION, file_path="/b.py", line_start=1, line_end=5),
        )
        edge = CodeEdge(source="a", target="b", edge_type=EdgeType.CALLS, confidence=0.85)

        # to_dict includes confidence
        d = edge.to_dict()
        assert d["confidence"] == 0.85  # noqa: PLR2004

        # Round-trip through node-link serialization
        graph.add_edge(edge)
        data = graph.to_node_link_data()
        restored = CodeGraph.from_node_link_data(data)
        edges = list(restored._graph.edges(data=True))
        assert len(edges) == 1
        assert edges[0][2]["confidence"] == 0.85  # noqa: PLR2004

    def test_add_edge_stores_confidence(self) -> None:
        """Test that add_edge passes confidence to the NetworkX graph."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(id="a", name="a", node_type=NodeType.FUNCTION, file_path="/a.py", line_start=1, line_end=5),
        )
        graph.add_node(
            CodeNode(id="b", name="b", node_type=NodeType.FUNCTION, file_path="/b.py", line_start=1, line_end=5),
        )
        graph.add_edge(CodeEdge(source="a", target="b", edge_type=EdgeType.CALLS, confidence=0.60))

        edge_data = graph._graph.edges["a", "b", "calls"]
        assert edge_data["confidence"] == 0.60  # noqa: PLR2004

    def test_get_view_preserves_max_confidence(self) -> None:
        """Test that get_view takes max confidence across parallel edges."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(id="a", name="a", node_type=NodeType.FUNCTION, file_path="/a.py", line_start=1, line_end=5),
        )
        graph.add_node(
            CodeNode(id="b", name="b", node_type=NodeType.FUNCTION, file_path="/b.py", line_start=1, line_end=5),
        )
        graph.add_edge(CodeEdge(source="a", target="b", edge_type=EdgeType.CALLS, confidence=0.60))
        graph.add_edge(CodeEdge(source="a", target="b", edge_type=EdgeType.REFERENCES, confidence=0.95))

        view = graph.get_view()
        assert view["a"]["b"]["confidence"] == 0.95  # noqa: PLR2004


class TestCodeGraph:
    """Tests for CodeGraph class."""

    def test_create_empty_graph(self) -> None:
        """Test creating an empty graph."""
        graph = CodeGraph()
        assert len(graph) == 0
        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_add_node(self) -> None:
        """Test adding a node to the graph."""
        graph = CodeGraph()
        node = CodeNode(
            id="test:node",
            name="test",
            node_type=NodeType.FUNCTION,
            file_path="/test.py",
            line_start=1,
            line_end=5,
        )
        graph.add_node(node)
        assert graph.node_count == 1
        assert graph.has_node("test:node")

    def test_add_edge(self) -> None:
        """Test adding an edge to the graph."""
        graph = CodeGraph()

        # Add nodes first
        node_a = CodeNode(id="a", name="a", node_type=NodeType.FUNCTION, file_path="/a.py", line_start=1, line_end=5)
        node_b = CodeNode(id="b", name="b", node_type=NodeType.FUNCTION, file_path="/b.py", line_start=1, line_end=5)
        graph.add_node(node_a)
        graph.add_node(node_b)

        # Add edge
        edge = CodeEdge(source="a", target="b", edge_type=EdgeType.CALLS)
        graph.add_edge(edge)

        assert graph.edge_count == 1
        assert graph.has_edge("a", "b")
        assert graph.has_edge("a", "b", EdgeType.CALLS)

    def test_get_node_data(self) -> None:
        """Test retrieving node data."""
        graph = CodeGraph()
        node = CodeNode(
            id="test",
            name="test_func",
            node_type=NodeType.FUNCTION,
            file_path="/test.py",
            line_start=10,
            line_end=20,
        )
        graph.add_node(node)

        data = graph.get_node_data("test")
        assert data is not None
        assert data["name"] == "test_func"
        assert data["node_type"] == "function"

    def test_get_nodes_by_type(self) -> None:
        """Test filtering nodes by type."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="f1",
                name="f1",
                node_type=NodeType.FUNCTION,
                file_path="/a.py",
                line_start=1,
                line_end=5,
            ),
        )
        graph.add_node(
            CodeNode(
                id="f2",
                name="f2",
                node_type=NodeType.FUNCTION,
                file_path="/b.py",
                line_start=1,
                line_end=5,
            ),
        )
        graph.add_node(
            CodeNode(
                id="c1",
                name="c1",
                node_type=NodeType.CLASS,
                file_path="/c.py",
                line_start=1,
                line_end=10,
            ),
        )

        functions = graph.get_nodes_by_type(NodeType.FUNCTION)
        assert len(functions) == 2  # noqa: PLR2004
        assert "f1" in functions
        assert "f2" in functions

    def test_get_view_filters_edges(self) -> None:
        """Test that get_view filters by edge type."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="a",
                name="a",
                node_type=NodeType.FUNCTION,
                file_path="/a.py",
                line_start=1,
                line_end=5,
            ),
        )
        graph.add_node(
            CodeNode(
                id="b",
                name="b",
                node_type=NodeType.FUNCTION,
                file_path="/b.py",
                line_start=1,
                line_end=5,
            ),
        )
        graph.add_node(
            CodeNode(
                id="c",
                name="c",
                node_type=NodeType.FUNCTION,
                file_path="/c.py",
                line_start=1,
                line_end=5,
            ),
        )

        graph.add_edge(CodeEdge(source="a", target="b", edge_type=EdgeType.CALLS))
        graph.add_edge(CodeEdge(source="a", target="c", edge_type=EdgeType.IMPORTS))

        # Get view with only CALLS
        calls_view = graph.get_view([EdgeType.CALLS])
        assert calls_view.has_edge("a", "b")
        assert not calls_view.has_edge("a", "c")

    def test_node_link_roundtrip(self) -> None:
        """Test exporting and importing graph as node-link data."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="a",
                name="a",
                node_type=NodeType.FUNCTION,
                file_path="/a.py",
                line_start=1,
                line_end=5,
            ),
        )
        graph.add_node(
            CodeNode(
                id="b",
                name="b",
                node_type=NodeType.FUNCTION,
                file_path="/b.py",
                line_start=1,
                line_end=5,
            ),
        )
        graph.add_edge(CodeEdge(source="a", target="b", edge_type=EdgeType.CALLS))

        # Export
        data = graph.to_node_link_data()
        assert "nodes" in data
        # NetworkX 3.x uses "edges" instead of "links"
        assert "edges" in data

        # Import
        restored = CodeGraph.from_node_link_data(data)
        assert restored.node_count == 2  # noqa: PLR2004
        assert restored.edge_count == 1
        assert restored.has_edge("a", "b")

    def test_describe(self) -> None:
        """Test the describe method returns a summary dict."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="a",
                name="a",
                node_type=NodeType.FUNCTION,
                file_path="/a.py",
                line_start=1,
                line_end=5,
            ),
        )
        graph.add_node(
            CodeNode(
                id="b",
                name="b",
                node_type=NodeType.CLASS,
                file_path="/b.py",
                line_start=1,
                line_end=10,
            ),
        )
        graph.add_edge(CodeEdge(source="a", target="b", edge_type=EdgeType.CALLS))

        desc = graph.describe()
        assert desc["node_count"] == 2  # noqa: PLR2004
        assert desc["edge_count"] == 1
        assert desc["node_types"]["function"] == 1
        assert desc["node_types"]["class"] == 1
        assert desc["edge_types"]["calls"] == 1
        assert isinstance(desc["density"], float)

    def test_describe_empty_graph(self) -> None:
        """Test describe on an empty graph."""
        graph = CodeGraph()
        desc = graph.describe()
        assert desc["node_count"] == 0
        assert desc["edge_count"] == 0
        assert desc["node_types"] == {}
        assert desc["edge_types"] == {}

    def test_from_node_link_data_legacy_links_format(self) -> None:
        """Test that from_node_link_data handles the old 'links' format."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="x",
                name="x",
                node_type=NodeType.FUNCTION,
                file_path="/x.py",
                line_start=1,
                line_end=5,
            ),
        )
        graph.add_node(
            CodeNode(
                id="y",
                name="y",
                node_type=NodeType.FUNCTION,
                file_path="/y.py",
                line_start=1,
                line_end=5,
            ),
        )
        graph.add_edge(CodeEdge(source="x", target="y", edge_type=EdgeType.CALLS))

        # Export and manually convert "edges" to "links" to simulate old format
        data = graph.to_node_link_data()
        if "edges" in data:
            data["links"] = data.pop("edges")

        restored = CodeGraph.from_node_link_data(data)
        assert restored.node_count == 2  # noqa: PLR2004
        assert restored.edge_count == 1
        assert restored.has_edge("x", "y")
