from __future__ import annotations

import pytest

from code_context_agent.tools.graph.model import CodeEdge, CodeGraph, CodeNode, EdgeType, NodeType
from code_context_agent.tools.graph.storage import KuzuStorage, NetworkXStorage


def _make_node(node_id: str, name: str, node_type: NodeType = NodeType.FUNCTION) -> CodeNode:
    return CodeNode(id=node_id, name=name, node_type=node_type, file_path="src/main.py", line_start=1, line_end=10)


def _make_edge(src: str, tgt: str, edge_type: EdgeType = EdgeType.CALLS) -> CodeEdge:
    return CodeEdge(source=src, target=tgt, edge_type=edge_type)


# ---------------------------------------------------------------------------
# NetworkXStorage
# ---------------------------------------------------------------------------


class TestNetworkXStorage:
    def test_delegates_add_and_query(self) -> None:
        storage = NetworkXStorage()
        node = _make_node("a:foo", "foo")
        storage.add_node(node)
        assert storage.has_node("a:foo")
        data = storage.get_node_data("a:foo")
        assert data is not None
        assert data["name"] == "foo"

        edge = _make_edge("a:foo", "a:bar")
        storage.add_node(_make_node("a:bar", "bar"))
        storage.add_edge(edge)
        assert storage.edge_count() == 1

    def test_describe_returns_counts(self) -> None:
        storage = NetworkXStorage()
        storage.add_node(_make_node("a:foo", "foo"))
        storage.add_node(_make_node("a:bar", "bar", NodeType.CLASS))
        storage.add_edge(_make_edge("a:foo", "a:bar"))
        desc = storage.describe()
        assert desc["node_count"] == 2
        assert desc["edge_count"] == 1
        assert "function" in desc["node_types"]


# ---------------------------------------------------------------------------
# KuzuStorage
# ---------------------------------------------------------------------------


class TestKuzuStorage:
    def test_add_node(self, tmp_path: object) -> None:
        storage = KuzuStorage(tmp_path / "db")  # type: ignore[operator]
        node = _make_node("a:foo", "foo")
        storage.add_node(node)
        assert storage.has_node("a:foo")
        assert storage.node_count() == 1

    def test_add_edge(self, tmp_path: object) -> None:
        storage = KuzuStorage(tmp_path / "db")  # type: ignore[operator]
        storage.add_node(_make_node("a:foo", "foo"))
        storage.add_node(_make_node("a:bar", "bar"))
        storage.add_edge(_make_edge("a:foo", "a:bar"))
        assert storage.edge_count() == 1

    def test_get_nodes_by_type(self, tmp_path: object) -> None:
        storage = KuzuStorage(tmp_path / "db")  # type: ignore[operator]
        storage.add_node(_make_node("a:foo", "foo", NodeType.FUNCTION))
        storage.add_node(_make_node("a:bar", "bar", NodeType.CLASS))
        storage.add_node(_make_node("a:baz", "baz", NodeType.FUNCTION))
        funcs = storage.get_nodes_by_type(NodeType.FUNCTION)
        assert sorted(funcs) == ["a:baz", "a:foo"]

    def test_get_edges_by_type(self, tmp_path: object) -> None:
        storage = KuzuStorage(tmp_path / "db")  # type: ignore[operator]
        storage.add_node(_make_node("a:foo", "foo"))
        storage.add_node(_make_node("a:bar", "bar"))
        storage.add_edge(_make_edge("a:foo", "a:bar", EdgeType.CALLS))
        storage.add_edge(_make_edge("a:foo", "a:bar", EdgeType.IMPORTS))
        calls = storage.get_edges_by_type(EdgeType.CALLS)
        assert len(calls) == 1
        assert calls[0][0] == "a:foo"
        assert calls[0][1] == "a:bar"

    def test_execute_cypher(self, tmp_path: object) -> None:
        storage = KuzuStorage(tmp_path / "db")  # type: ignore[operator]
        storage.add_node(_make_node("a:foo", "foo"))
        storage.add_node(_make_node("a:bar", "bar"))
        rows = storage.execute_cypher("MATCH (n:CodeNode) RETURN n.id ORDER BY n.id")
        assert len(rows) == 2
        assert rows[0][0] == "a:bar"
        assert rows[1][0] == "a:foo"

    def test_blocks_writes(self, tmp_path: object) -> None:
        storage = KuzuStorage(tmp_path / "db")  # type: ignore[operator]
        with pytest.raises(ValueError, match="Write operations are not allowed"):
            storage.execute_cypher("CREATE (n:CodeNode {id: 'x'})")
        with pytest.raises(ValueError, match="Write operations are not allowed"):
            storage.execute_cypher("MATCH (n) DELETE n")
        with pytest.raises(ValueError, match="Write operations are not allowed"):
            storage.execute_cypher("MATCH (n:CodeNode) SET n.name = 'x'")

    def test_to_code_graph(self, tmp_path: object) -> None:
        storage = KuzuStorage(tmp_path / "db")  # type: ignore[operator]
        storage.add_node(_make_node("a:foo", "foo"))
        storage.add_node(_make_node("a:bar", "bar"))
        storage.add_edge(_make_edge("a:foo", "a:bar"))
        graph = storage.to_code_graph()
        assert isinstance(graph, CodeGraph)
        assert graph.node_count == 2
        assert graph.edge_count == 1
        assert graph.has_node("a:foo")
        assert graph.has_edge("a:foo", "a:bar")

    def test_describe(self, tmp_path: object) -> None:
        storage = KuzuStorage(tmp_path / "db")  # type: ignore[operator]
        storage.add_node(_make_node("a:foo", "foo", NodeType.FUNCTION))
        storage.add_node(_make_node("a:bar", "bar", NodeType.CLASS))
        storage.add_edge(_make_edge("a:foo", "a:bar"))
        desc = storage.describe()
        assert desc["node_count"] == 2
        assert desc["edge_count"] == 1
        assert desc["backend"] == "kuzu"
        assert "function" in desc["node_types"]
        assert "class" in desc["node_types"]
