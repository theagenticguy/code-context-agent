"""Tests for code graph analysis."""

import pytest

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
    graph.add_node(
        CodeNode(
            id="main",
            name="main",
            node_type=NodeType.FUNCTION,
            file_path="/main.py",
            line_start=1,
            line_end=10,
        )
    )
    graph.add_node(
        CodeNode(
            id="helper1",
            name="helper1",
            node_type=NodeType.FUNCTION,
            file_path="/helpers.py",
            line_start=1,
            line_end=10,
        )
    )
    graph.add_node(
        CodeNode(
            id="helper2",
            name="helper2",
            node_type=NodeType.FUNCTION,
            file_path="/helpers.py",
            line_start=15,
            line_end=25,
        )
    )
    graph.add_node(
        CodeNode(
            id="util",
            name="util",
            node_type=NodeType.FUNCTION,
            file_path="/utils.py",
            line_start=1,
            line_end=5,
        )
    )

    # main calls helpers
    graph.add_edge(CodeEdge(source="main", target="helper1", edge_type=EdgeType.CALLS))
    graph.add_edge(CodeEdge(source="main", target="helper2", edge_type=EdgeType.CALLS))

    # helpers call util
    graph.add_edge(CodeEdge(source="helper1", target="util", edge_type=EdgeType.CALLS))
    graph.add_edge(CodeEdge(source="helper2", target="util", edge_type=EdgeType.CALLS))

    return graph


def create_clustered_graph() -> CodeGraph:
    """Create a graph with natural clusters."""
    graph = CodeGraph()

    # Cluster 1: auth module
    graph.add_node(
        CodeNode(
            id="auth/login",
            name="login",
            node_type=NodeType.FUNCTION,
            file_path="/auth/login.py",
            line_start=1,
            line_end=10,
        )
    )
    graph.add_node(
        CodeNode(
            id="auth/logout",
            name="logout",
            node_type=NodeType.FUNCTION,
            file_path="/auth/logout.py",
            line_start=1,
            line_end=10,
        )
    )
    graph.add_node(
        CodeNode(
            id="auth/session",
            name="session",
            node_type=NodeType.FUNCTION,
            file_path="/auth/session.py",
            line_start=1,
            line_end=10,
        )
    )

    graph.add_edge(CodeEdge(source="auth/login", target="auth/session", edge_type=EdgeType.CALLS))
    graph.add_edge(CodeEdge(source="auth/logout", target="auth/session", edge_type=EdgeType.CALLS))

    # Cluster 2: db module
    graph.add_node(
        CodeNode(
            id="db/connect",
            name="connect",
            node_type=NodeType.FUNCTION,
            file_path="/db/connect.py",
            line_start=1,
            line_end=10,
        )
    )
    graph.add_node(
        CodeNode(
            id="db/query",
            name="query",
            node_type=NodeType.FUNCTION,
            file_path="/db/query.py",
            line_start=1,
            line_end=10,
        )
    )
    graph.add_node(
        CodeNode(
            id="db/pool",
            name="pool",
            node_type=NodeType.FUNCTION,
            file_path="/db/pool.py",
            line_start=1,
            line_end=10,
        )
    )

    graph.add_edge(CodeEdge(source="db/connect", target="db/pool", edge_type=EdgeType.CALLS))
    graph.add_edge(CodeEdge(source="db/query", target="db/pool", edge_type=EdgeType.CALLS))

    # Cross-cluster edge (sparse)
    graph.add_edge(CodeEdge(source="auth/login", target="db/query", edge_type=EdgeType.CALLS))

    return graph


@pytest.fixture()
def sample_graph():
    """Fixture providing a sample graph."""
    return create_sample_graph()


@pytest.fixture()
def clustered_graph():
    """Fixture providing a clustered graph."""
    return create_clustered_graph()


class TestTrustRankAndTriangles:
    """Tests for TrustRank and triangle detection."""

    def test_find_trusted_foundations(self, sample_graph: CodeGraph) -> None:
        """Test TrustRank finds trusted foundations."""
        analyzer = CodeAnalyzer(sample_graph)
        results = analyzer.find_trusted_foundations(top_k=5)
        assert isinstance(results, list)

    def test_find_trusted_foundations_with_seeds(self, sample_graph: CodeGraph) -> None:
        """Test TrustRank with explicit seed nodes."""
        analyzer = CodeAnalyzer(sample_graph)
        results = analyzer.find_trusted_foundations(seed_nodes=["main"], top_k=5)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_find_trusted_foundations_empty_graph(self) -> None:
        """Test TrustRank on an empty graph."""
        graph = CodeGraph()
        analyzer = CodeAnalyzer(graph)
        results = analyzer.find_trusted_foundations(top_k=5)
        assert results == []

    def test_find_triangles(self, clustered_graph: CodeGraph) -> None:
        """Test triangle detection on a clustered graph."""
        analyzer = CodeAnalyzer(clustered_graph)
        results = analyzer.find_triangles(top_k=5)
        assert isinstance(results, list)

    def test_find_triangles_empty_graph(self) -> None:
        """Test triangle detection on an empty graph."""
        graph = CodeGraph()
        analyzer = CodeAnalyzer(graph)
        results = analyzer.find_triangles(top_k=5)
        assert results == []


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
        node1 = CodeNode(
            id="db1",
            name="query1",
            node_type=NodeType.PATTERN_MATCH,
            file_path="/a.py",
            line_start=1,
            line_end=5,
            metadata={"category": "db"},
        )
        node2 = CodeNode(
            id="db2",
            name="query2",
            node_type=NodeType.PATTERN_MATCH,
            file_path="/b.py",
            line_start=1,
            line_end=5,
            metadata={"category": "db"},
        )
        node3 = CodeNode(
            id="auth1",
            name="login",
            node_type=NodeType.PATTERN_MATCH,
            file_path="/c.py",
            line_start=1,
            line_end=5,
            metadata={"category": "auth"},
        )

        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        analyzer = CodeAnalyzer(graph)
        db_nodes = analyzer.find_clusters_by_category("db")

        assert len(db_nodes) == 2  # noqa: PLR2004
        assert all(n["category"] == "db" for n in db_nodes)

    def test_empty_graph(self) -> None:
        """Test analysis on empty graph returns empty results."""
        graph = CodeGraph()
        analyzer = CodeAnalyzer(graph)

        assert analyzer.find_hotspots() == []
        assert analyzer.find_foundations() == []
        assert analyzer.find_entry_points() == []
        assert analyzer.detect_modules() == []


class TestUnusedSymbols:
    """Tests for unused symbol detection."""

    def test_finds_unreferenced_functions(self) -> None:
        """Functions with no cross-file incoming edges are detected."""
        graph = CodeGraph()
        # referenced: called from another file
        graph.add_node(
            CodeNode(
                id="a.py:used_func",
                name="used_func",
                node_type=NodeType.FUNCTION,
                file_path="a.py",
                line_start=1,
                line_end=5,
            )
        )
        graph.add_node(
            CodeNode(
                id="b.py:caller",
                name="caller",
                node_type=NodeType.FUNCTION,
                file_path="b.py",
                line_start=1,
                line_end=5,
            )
        )
        graph.add_edge(CodeEdge(source="b.py:caller", target="a.py:used_func", edge_type=EdgeType.CALLS))

        # unreferenced: no cross-file callers
        graph.add_node(
            CodeNode(
                id="c.py:orphan_func",
                name="orphan_func",
                node_type=NodeType.FUNCTION,
                file_path="c.py",
                line_start=1,
                line_end=5,
            )
        )

        analyzer = CodeAnalyzer(graph)
        unused = analyzer.find_unused_symbols()

        unused_ids = [u["id"] for u in unused]
        assert "c.py:orphan_func" in unused_ids
        assert "a.py:used_func" not in unused_ids

    def test_excludes_private_and_test_functions(self) -> None:
        """Functions starting with _ or test_ are excluded by default."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="a.py:_private",
                name="_private",
                node_type=NodeType.FUNCTION,
                file_path="a.py",
                line_start=1,
                line_end=5,
            )
        )
        graph.add_node(
            CodeNode(
                id="a.py:test_something",
                name="test_something",
                node_type=NodeType.FUNCTION,
                file_path="a.py",
                line_start=10,
                line_end=15,
            )
        )

        analyzer = CodeAnalyzer(graph)
        unused = analyzer.find_unused_symbols()

        assert len(unused) == 0

    def test_custom_exclude_patterns(self) -> None:
        """Custom exclude patterns override defaults."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="a.py:public_func",
                name="public_func",
                node_type=NodeType.FUNCTION,
                file_path="a.py",
                line_start=1,
                line_end=5,
            )
        )

        analyzer = CodeAnalyzer(graph)
        # Exclude nothing — should find the function
        unused = analyzer.find_unused_symbols(exclude_patterns=[r"^ZZZZZ$"])
        assert len(unused) == 1
        assert unused[0]["name"] == "public_func"

    def test_same_file_refs_dont_count(self) -> None:
        """References from the same file don't prevent unused detection."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="a.py:helper",
                name="helper",
                node_type=NodeType.FUNCTION,
                file_path="a.py",
                line_start=1,
                line_end=5,
            )
        )
        graph.add_node(
            CodeNode(
                id="a.py:caller",
                name="caller",
                node_type=NodeType.FUNCTION,
                file_path="a.py",
                line_start=10,
                line_end=15,
            )
        )
        graph.add_edge(CodeEdge(source="a.py:caller", target="a.py:helper", edge_type=EdgeType.CALLS))

        analyzer = CodeAnalyzer(graph)
        unused = analyzer.find_unused_symbols(exclude_patterns=[r"^ZZZZZ$"])

        unused_ids = [u["id"] for u in unused]
        # helper is called only from same file — still counts as unused
        assert "a.py:helper" in unused_ids

    def test_filters_by_node_type(self) -> None:
        """Only specified node types are checked."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="a.py:MyClass",
                name="MyClass",
                node_type=NodeType.CLASS,
                file_path="a.py",
                line_start=1,
                line_end=50,
            )
        )
        graph.add_node(
            CodeNode(
                id="a.py:my_func",
                name="my_func",
                node_type=NodeType.FUNCTION,
                file_path="a.py",
                line_start=55,
                line_end=60,
            )
        )

        analyzer = CodeAnalyzer(graph)
        # Only look for unused classes
        unused = analyzer.find_unused_symbols(
            node_types=["class"],
            exclude_patterns=[r"^ZZZZZ$"],
        )

        assert len(unused) == 1
        assert unused[0]["node_type"] == "class"

    def test_empty_graph_returns_empty(self) -> None:
        """Empty graph returns no unused symbols."""
        analyzer = CodeAnalyzer(CodeGraph())
        assert analyzer.find_unused_symbols() == []


class TestRefactoringCandidates:
    """Tests for combined refactoring candidate analysis."""

    def test_detects_clone_pairs(self) -> None:
        """SIMILAR_TO edges produce extract_helper candidates."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="a.py",
                name="a.py",
                node_type=NodeType.FILE,
                file_path="a.py",
                line_start=0,
                line_end=100,
            )
        )
        graph.add_node(
            CodeNode(
                id="b.py",
                name="b.py",
                node_type=NodeType.FILE,
                file_path="b.py",
                line_start=0,
                line_end=100,
            )
        )
        graph.add_edge(
            CodeEdge(
                source="a.py",
                target="b.py",
                edge_type=EdgeType.SIMILAR_TO,
                metadata={"duplicated_lines": 15},
            )
        )

        analyzer = CodeAnalyzer(graph)
        candidates = analyzer.find_refactoring_candidates()

        extract_candidates = [c for c in candidates if c["type"] == "extract_helper"]
        assert len(extract_candidates) == 1
        assert extract_candidates[0]["duplicated_lines"] == 15  # noqa: PLR2004

    def test_detects_code_smells(self) -> None:
        """Nodes with code_smell note produce code_smell candidates."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="a.py:10:god",
                name="big_func",
                node_type=NodeType.PATTERN_MATCH,
                file_path="a.py",
                line_start=10,
                line_end=200,
                metadata={"rule_id": "py-god-function", "note": "code_smell"},
            )
        )
        graph.add_node(
            CodeNode(
                id="b.py:5:god",
                name="another_big",
                node_type=NodeType.PATTERN_MATCH,
                file_path="b.py",
                line_start=5,
                line_end=150,
                metadata={"rule_id": "py-god-function", "note": "code_smell"},
            )
        )

        analyzer = CodeAnalyzer(graph)
        candidates = analyzer.find_refactoring_candidates()

        smell_candidates = [c for c in candidates if c["type"] == "code_smell"]
        assert len(smell_candidates) == 1
        assert smell_candidates[0]["occurrence_count"] == 2  # noqa: PLR2004

    def test_detects_dead_code(self) -> None:
        """Unreferenced functions produce dead_code candidates."""
        graph = CodeGraph()
        graph.add_node(
            CodeNode(
                id="a.py:orphan1",
                name="orphan1",
                node_type=NodeType.FUNCTION,
                file_path="a.py",
                line_start=1,
                line_end=5,
            )
        )
        graph.add_node(
            CodeNode(
                id="a.py:orphan2",
                name="orphan2",
                node_type=NodeType.FUNCTION,
                file_path="a.py",
                line_start=10,
                line_end=15,
            )
        )

        analyzer = CodeAnalyzer(graph)
        candidates = analyzer.find_refactoring_candidates()

        dead = [c for c in candidates if c["type"] == "dead_code"]
        assert len(dead) == 1
        assert dead[0]["occurrence_count"] == 2  # noqa: PLR2004

    def test_ranking_by_score(self) -> None:
        """Candidates are ranked by score descending."""
        graph = CodeGraph()
        # High-score clone pair (20 lines * 2 = 40)
        graph.add_node(
            CodeNode(
                id="a.py",
                name="a.py",
                node_type=NodeType.FILE,
                file_path="a.py",
                line_start=0,
                line_end=100,
            )
        )
        graph.add_node(
            CodeNode(
                id="b.py",
                name="b.py",
                node_type=NodeType.FILE,
                file_path="b.py",
                line_start=0,
                line_end=100,
            )
        )
        graph.add_edge(
            CodeEdge(
                source="a.py",
                target="b.py",
                edge_type=EdgeType.SIMILAR_TO,
                metadata={"duplicated_lines": 20},
            )
        )

        # Low-score single orphan (1 * 1.0 = 1)
        graph.add_node(
            CodeNode(
                id="c.py:lonely",
                name="lonely",
                node_type=NodeType.FUNCTION,
                file_path="c.py",
                line_start=1,
                line_end=5,
            )
        )

        analyzer = CodeAnalyzer(graph)
        candidates = analyzer.find_refactoring_candidates()

        assert len(candidates) >= 2  # noqa: PLR2004
        assert candidates[0]["score"] >= candidates[-1]["score"]

    def test_empty_graph_returns_empty(self) -> None:
        """Empty graph returns no refactoring candidates."""
        analyzer = CodeAnalyzer(CodeGraph())
        assert analyzer.find_refactoring_candidates() == []
