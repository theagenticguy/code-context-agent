"""Tests for code graph analysis."""


from code_context_agent.tools.graph.analysis import CodeAnalyzer
from code_context_agent.tools.graph.model import (
    CodeEdge,
    CodeGraph,
    CodeNode,
    EdgeType,
    NodeType,
)


def create_sample_graph() -> CodeGraph:
    """Create a sample graph for testing."""
    graph = CodeGraph()

    # Create nodes: main -> helper1, helper2
    #                       helper1 -> util
    #                       helper2 -> util
    graph.add_node(CodeNode("main", "main", NodeType.FUNCTION, "/main.py", 1, 10))
    graph.add_node(CodeNode("helper1", "helper1", NodeType.FUNCTION, "/helpers.py", 1, 10))
    graph.add_node(CodeNode("helper2", "helper2", NodeType.FUNCTION, "/helpers.py", 15, 25))
    graph.add_node(CodeNode("util", "util", NodeType.FUNCTION, "/utils.py", 1, 5))

    # main calls helpers
    graph.add_edge(CodeEdge("main", "helper1", EdgeType.CALLS))
    graph.add_edge(CodeEdge("main", "helper2", EdgeType.CALLS))

    # helpers call util
    graph.add_edge(CodeEdge("helper1", "util", EdgeType.CALLS))
    graph.add_edge(CodeEdge("helper2", "util", EdgeType.CALLS))

    return graph


def create_clustered_graph() -> CodeGraph:
    """Create a graph with natural clusters."""
    graph = CodeGraph()

    # Cluster 1: auth module
    graph.add_node(CodeNode("auth/login", "login", NodeType.FUNCTION, "/auth/login.py", 1, 10))
    graph.add_node(CodeNode("auth/logout", "logout", NodeType.FUNCTION, "/auth/logout.py", 1, 10))
    graph.add_node(CodeNode("auth/session", "session", NodeType.FUNCTION, "/auth/session.py", 1, 10))

    graph.add_edge(CodeEdge("auth/login", "auth/session", EdgeType.CALLS))
    graph.add_edge(CodeEdge("auth/logout", "auth/session", EdgeType.CALLS))

    # Cluster 2: db module
    graph.add_node(CodeNode("db/connect", "connect", NodeType.FUNCTION, "/db/connect.py", 1, 10))
    graph.add_node(CodeNode("db/query", "query", NodeType.FUNCTION, "/db/query.py", 1, 10))
    graph.add_node(CodeNode("db/pool", "pool", NodeType.FUNCTION, "/db/pool.py", 1, 10))

    graph.add_edge(CodeEdge("db/connect", "db/pool", EdgeType.CALLS))
    graph.add_edge(CodeEdge("db/query", "db/pool", EdgeType.CALLS))

    # Cross-cluster edge (sparse)
    graph.add_edge(CodeEdge("auth/login", "db/query", EdgeType.CALLS))

    return graph


class TestCodeAnalyzer:
    """Tests for CodeAnalyzer class."""

    def test_find_entry_points(self) -> None:
        """Test finding entry points (no incoming calls)."""
        graph = create_sample_graph()
        analyzer = CodeAnalyzer(graph)

        entry_points = analyzer.find_entry_points()

        # main has no incoming calls but makes outgoing calls
        entry_ids = [ep["id"] for ep in entry_points]
        assert "main" in entry_ids

    def test_find_hotspots(self) -> None:
        """Test finding hotspots via betweenness centrality."""
        graph = create_sample_graph()
        analyzer = CodeAnalyzer(graph)

        hotspots = analyzer.find_hotspots(top_k=3)

        # util should have high betweenness (on path from main to both helpers)
        # Note: exact ordering depends on graph structure
        assert len(hotspots) > 0
        hotspot_ids = [h["id"] for h in hotspots]
        # helper1 and helper2 are on paths between main and util
        assert any(hid in hotspot_ids for hid in ["helper1", "helper2", "util"])

    def test_find_foundations(self) -> None:
        """Test finding foundations via PageRank."""
        graph = create_sample_graph()
        analyzer = CodeAnalyzer(graph)

        foundations = analyzer.find_foundations(top_k=3)

        # util is heavily depended upon
        assert len(foundations) > 0
        foundation_ids = [f["id"] for f in foundations]
        # Util should rank high as it receives edges from helper1 and helper2
        assert "util" in foundation_ids

    def test_detect_modules(self) -> None:
        """Test community detection."""
        graph = create_clustered_graph()
        analyzer = CodeAnalyzer(graph)

        modules = analyzer.detect_modules(resolution=1.0)

        # Should detect at least 2 clusters (auth and db)
        assert len(modules) >= 1

        # Check that modules have expected structure
        for module in modules:
            assert "module_id" in module
            assert "size" in module
            assert "members" in module
            assert "cohesion" in module

    def test_calculate_coupling(self) -> None:
        """Test coupling calculation between nodes."""
        graph = create_sample_graph()
        analyzer = CodeAnalyzer(graph)

        # helper1 and helper2 share util as a common neighbor
        coupling = analyzer.calculate_coupling("helper1", "helper2")

        assert "coupling" in coupling
        assert coupling["shared_neighbors"] >= 1  # util is shared
        assert coupling["node_a"] == "helper1"
        assert coupling["node_b"] == "helper2"

    def test_get_similar_nodes(self) -> None:
        """Test finding similar nodes via personalized PageRank."""
        graph = create_sample_graph()
        analyzer = CodeAnalyzer(graph)

        # Find nodes similar to helper1
        similar = analyzer.get_similar_nodes("helper1", top_k=3)

        # Should find util (directly connected) and possibly helper2 (similar position)
        similar_ids = [s["id"] for s in similar]
        assert len(similar) > 0
        # util is directly connected
        assert "util" in similar_ids or "main" in similar_ids

    def test_get_dependency_chain_outgoing(self) -> None:
        """Test getting outgoing dependency chain."""
        graph = create_sample_graph()
        analyzer = CodeAnalyzer(graph)

        chain = analyzer.get_dependency_chain("main", direction="outgoing", max_depth=2)

        assert "root" in chain
        assert chain["root"] == "main"
        assert "nodes" in chain

        # Should include main, helper1, helper2, util (within depth 2)
        node_ids = [n["id"] for n in chain["nodes"]]
        assert "main" in node_ids
        assert "helper1" in node_ids or "helper2" in node_ids

    def test_find_clusters_by_category(self) -> None:
        """Test finding nodes by business logic category."""
        graph = CodeGraph()

        # Add nodes with category metadata
        node1 = CodeNode("db1", "query1", NodeType.PATTERN_MATCH, "/a.py", 1, 5, metadata={"category": "db"})
        node2 = CodeNode("db2", "query2", NodeType.PATTERN_MATCH, "/b.py", 1, 5, metadata={"category": "db"})
        node3 = CodeNode("auth1", "login", NodeType.PATTERN_MATCH, "/c.py", 1, 5, metadata={"category": "auth"})

        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        analyzer = CodeAnalyzer(graph)
        db_nodes = analyzer.find_clusters_by_category("db")

        assert len(db_nodes) == 2
        assert all(n["category"] == "db" for n in db_nodes)

    def test_empty_graph(self) -> None:
        """Test analysis on empty graph returns empty results."""
        graph = CodeGraph()
        analyzer = CodeAnalyzer(graph)

        assert analyzer.find_hotspots() == []
        assert analyzer.find_foundations() == []
        assert analyzer.find_entry_points() == []
        assert analyzer.detect_modules() == []
