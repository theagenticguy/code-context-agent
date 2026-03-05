"""Tests for code_graph_ingest_git tool."""

import json

from code_context_agent.tools.graph.tools import (
    _graphs,
    code_graph_create,
    code_graph_ingest_git,
)


def _make_hotspots_result():
    return json.dumps({
        "status": "success",
        "hotspots": [
            {"path": "src/auth.py", "commits": 42, "percentage": 15.3},
            {"path": "src/db.py", "commits": 30, "percentage": 10.8},
        ],
        "total_commits_analyzed": 200,
    })


def _make_cochanges_result():
    return json.dumps({
        "status": "success",
        "file_path": "src/auth.py",
        "total_commits": 42,
        "cochanged_files": [
            {"path": "src/db.py", "count": 25, "percentage": 59.5},
            {"path": "src/utils.py", "count": 8, "percentage": 19.0},
            {"path": "src/config.py", "count": 3, "percentage": 7.1},
        ],
    })


def _make_contributors_result():
    return json.dumps({
        "status": "success",
        "contributors": [
            {"email": "alice@example.com", "commits": 30, "percentage": 60.0},
            {"email": "bob@example.com", "commits": 20, "percentage": 40.0},
        ],
        "total_commits": 50,
    })


class TestCodeGraphIngestGitHotspots:
    def setup_method(self):
        _graphs.clear()
        code_graph_create("test")

    def test_adds_file_nodes(self):
        result = json.loads(code_graph_ingest_git("test", _make_hotspots_result(), "hotspots"))
        assert result["status"] == "success"
        assert result["nodes_added"] == 2
        assert result["total_nodes"] == 2

    def test_merges_metadata_on_existing_node(self):
        # First ingest creates nodes
        code_graph_ingest_git("test", _make_hotspots_result(), "hotspots")
        # Second ingest updates existing nodes
        result = json.loads(code_graph_ingest_git("test", _make_hotspots_result(), "hotspots"))
        assert result["nodes_added"] == 0
        assert result["nodes_updated"] == 2

    def test_skips_error_result(self):
        error_result = json.dumps({"status": "error", "message": "not a repo"})
        result = json.loads(code_graph_ingest_git("test", error_result, "hotspots"))
        assert result["status"] == "success"
        assert result["nodes_added"] == 0


class TestCodeGraphIngestGitCochanges:
    def setup_method(self):
        _graphs.clear()
        code_graph_create("test")

    def test_creates_edges(self):
        result = json.loads(code_graph_ingest_git("test", _make_cochanges_result(), "cochanges"))
        assert result["status"] == "success"
        assert result["edges_added"] == 1  # Only src/db.py at 59.5% passes default 20% threshold

    def test_respects_min_percentage(self):
        result = json.loads(
            code_graph_ingest_git("test", _make_cochanges_result(), "cochanges", min_percentage=5.0)
        )
        assert result["edges_added"] == 3  # All three pass 5% threshold (59.5%, 19.0%, 7.1%)


class TestCodeGraphIngestGitContributors:
    def setup_method(self):
        _graphs.clear()
        code_graph_create("test")

    def test_returns_metadata(self):
        result = json.loads(code_graph_ingest_git("test", _make_contributors_result(), "contributors"))
        assert result["status"] == "success"

    def test_attaches_to_existing_node(self):
        # First add a node
        code_graph_ingest_git("test", _make_hotspots_result(), "hotspots")
        # Then attach contributors
        result = json.loads(
            code_graph_ingest_git("test", _make_contributors_result(), "contributors", source_file="src/auth.py")
        )
        assert result["status"] == "success"
        # Verify metadata was attached
        node_data = _graphs["test"]._graph.nodes["src/auth.py"]
        assert "primary_author" in node_data.get("metadata", {})


class TestCodeGraphIngestGitErrors:
    def setup_method(self):
        _graphs.clear()

    def test_graph_not_found(self):
        result = json.loads(code_graph_ingest_git("nonexistent", _make_hotspots_result(), "hotspots"))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_invalid_json(self):
        _graphs.clear()
        code_graph_create("test")
        result = json.loads(code_graph_ingest_git("test", "not json", "hotspots"))
        assert result["status"] == "error"
        assert "Invalid JSON" in result["message"]

    def test_unknown_result_type(self):
        _graphs.clear()
        code_graph_create("test")
        result = json.loads(code_graph_ingest_git("test", "{}", "unknown_type"))
        assert result["status"] == "error"
        assert "Unknown result_type" in result["message"]
