"""Tests for graph adapters including git adapters."""

from code_context_agent.tools.graph.adapters import (
    ingest_clone_results,
    ingest_git_cochanges,
    ingest_git_contributors,
    ingest_git_hotspots,
    ingest_inheritance,
    ingest_lsp_definition,
    ingest_lsp_references,
    ingest_lsp_symbols,
)
from code_context_agent.tools.graph.model import EdgeType, NodeType


class TestAdapterConfidenceValues:
    """Tests for confidence values set by adapters."""

    def test_lsp_adapters_set_confidence_095(self) -> None:
        """Test that LSP reference/definition/symbol edges have confidence 0.95."""
        # LSP symbols (CONTAINS edges)
        symbols_result = {
            "status": "success",
            "symbols": [
                {
                    "name": "MyClass",
                    "kind": 5,
                    "range": {"start": {"line": 1}, "end": {"line": 20}},
                    "children": [
                        {
                            "name": "my_method",
                            "kind": 6,
                            "range": {"start": {"line": 2}, "end": {"line": 10}},
                            "children": [],
                        },
                    ],
                },
            ],
        }
        _, edges = ingest_lsp_symbols(symbols_result, "/src/foo.py")
        assert len(edges) == 1
        assert edges[0].confidence == 0.95  # noqa: PLR2004

        # LSP references (REFERENCES edges)
        refs_result = {
            "status": "success",
            "references": [
                {"uri": "file:///src/bar.py", "range": {"start": {"line": 5}, "end": {"line": 5}}},
            ],
        }
        ref_edges = ingest_lsp_references(refs_result, "src/foo.py:MyClass")
        assert len(ref_edges) == 1
        assert ref_edges[0].confidence == 0.95  # noqa: PLR2004

        # LSP definition (IMPORTS/CALLS edges)
        def_result = {
            "status": "success",
            "definitions": [
                {"uri": "file:///src/baz.py", "range": {"start": {"line": 10}, "end": {"line": 10}}},
            ],
        }
        def_edges = ingest_lsp_definition(def_result, "/src/foo.py", 5)
        assert len(def_edges) == 1
        assert def_edges[0].confidence == 0.95  # noqa: PLR2004

    def test_cochange_adapter_sets_confidence_060(self) -> None:
        """Test that cochange edges have confidence 0.60."""
        cochanges_result = {
            "status": "success",
            "file_path": "src/auth.py",
            "total_commits": 20,
            "cochanged_files": [
                {"path": "src/user.py", "count": 15, "percentage": 75.0},
            ],
        }
        edges = ingest_git_cochanges(cochanges_result)
        assert len(edges) == 1
        assert edges[0].confidence == 0.60  # noqa: PLR2004

    def test_inheritance_adapter_sets_confidence_085(self) -> None:
        """Test that inheritance edges have confidence 0.85."""
        edges = ingest_inheritance(
            "class Foo extends Bar implements IBaz",
            "src/foo.ts:Foo",
            "src/foo.ts",
        )
        assert len(edges) == 2  # noqa: PLR2004
        assert all(e.confidence == 0.85 for e in edges)  # noqa: PLR2004

    def test_clone_adapter_sets_confidence_075(self) -> None:
        """Test that clone/similar_to edges have confidence 0.75."""
        clone_result = {
            "status": "success",
            "clones": [
                {
                    "first_file": "src/a.py",
                    "second_file": "src/b.py",
                    "first_start": 1,
                    "first_end": 10,
                    "second_start": 5,
                    "second_end": 15,
                    "lines": 10,
                    "tokens": 50,
                    "fragment": "def foo(): pass",
                },
            ],
        }
        edges = ingest_clone_results(clone_result)
        assert len(edges) == 1
        assert edges[0].confidence == 0.75  # noqa: PLR2004


class TestIngestGitCochanges:
    """Tests for ingest_git_cochanges adapter."""

    def test_creates_edges_for_cochanged_files(self) -> None:
        """Test that it creates edges for files above threshold."""
        cochanges_result = {
            "status": "success",
            "file_path": "src/auth.py",
            "total_commits": 20,
            "cochanged_files": [
                {"path": "src/user.py", "count": 15, "percentage": 75.0},
                {"path": "src/session.py", "count": 10, "percentage": 50.0},
                {"path": "tests/test_auth.py", "count": 8, "percentage": 40.0},
                {"path": "README.md", "count": 2, "percentage": 10.0},  # Below threshold
            ],
        }

        edges = ingest_git_cochanges(cochanges_result, min_percentage=20.0)

        assert len(edges) == 3  # Only files above 20%  # noqa: PLR2004
        assert all(e.edge_type == EdgeType.COCHANGES for e in edges)
        assert all(e.source == "src/auth.py" for e in edges)

        # Check highest coupling file
        user_edge = next(e for e in edges if e.target == "src/user.py")
        assert user_edge.weight == 0.75  # noqa: PLR2004
        assert user_edge.metadata["percentage"] == 75.0  # noqa: PLR2004

    def test_respects_min_percentage(self) -> None:
        """Test that min_percentage filters edges."""
        cochanges_result = {
            "status": "success",
            "file_path": "src/main.py",
            "total_commits": 10,
            "cochanged_files": [
                {"path": "src/utils.py", "count": 6, "percentage": 60.0},
                {"path": "src/config.py", "count": 4, "percentage": 40.0},
            ],
        }

        edges_50 = ingest_git_cochanges(cochanges_result, min_percentage=50.0)
        edges_30 = ingest_git_cochanges(cochanges_result, min_percentage=30.0)

        assert len(edges_50) == 1
        assert len(edges_30) == 2  # noqa: PLR2004

    def test_handles_error_status(self) -> None:
        """Test that it returns empty list on error."""
        error_result = {"status": "error", "error": "git not found"}

        edges = ingest_git_cochanges(error_result)

        assert edges == []

    def test_handles_missing_file_path(self) -> None:
        """Test that it handles missing file_path gracefully."""
        result = {
            "status": "success",
            "cochanged_files": [{"path": "test.py", "count": 5, "percentage": 50.0}],
        }

        edges = ingest_git_cochanges(result)

        assert edges == []


class TestIngestGitHotspots:
    """Tests for ingest_git_hotspots adapter."""

    def test_creates_file_nodes(self) -> None:
        """Test that it creates FILE nodes for hotspots."""
        hotspots_result = {
            "status": "success",
            "hotspots": [
                {"path": "src/auth.py", "commits": 25, "percentage": 50.0},
                {"path": "src/api.py", "commits": 15, "percentage": 30.0},
            ],
            "total_commits_analyzed": 50,
        }

        nodes = ingest_git_hotspots(hotspots_result)

        assert len(nodes) == 2  # noqa: PLR2004
        assert all(n.node_type == NodeType.FILE for n in nodes)

        auth_node = next(n for n in nodes if "auth" in n.id)
        assert auth_node.metadata["commits"] == 25  # noqa: PLR2004
        assert auth_node.metadata["churn_percentage"] == 50.0  # noqa: PLR2004
        assert auth_node.metadata["source"] == "git_hotspots"

    def test_handles_error_status(self) -> None:
        """Test that it returns empty list on error."""
        error_result = {"status": "error", "error": "git not found"}

        nodes = ingest_git_hotspots(error_result)

        assert nodes == []

    def test_skips_empty_paths(self) -> None:
        """Test that it skips entries with empty paths."""
        result = {
            "status": "success",
            "hotspots": [
                {"path": "src/valid.py", "commits": 10, "percentage": 20.0},
                {"path": "", "commits": 5, "percentage": 10.0},
            ],
        }

        nodes = ingest_git_hotspots(result)

        assert len(nodes) == 1
        assert nodes[0].id == "src/valid.py"


class TestIngestGitContributors:
    """Tests for ingest_git_contributors adapter."""

    def test_extracts_contributor_metadata(self) -> None:
        """Test that it extracts contributor metadata."""
        contributors_result = {
            "status": "success",
            "contributors": [
                {
                    "email": "dev1@example.com",
                    "commits": 50,
                    "percentage": 50.0,
                    "first_commit": "2023-01-01",
                    "last_commit": "2024-01-15",
                },
                {
                    "email": "dev2@example.com",
                    "commits": 30,
                    "percentage": 30.0,
                    "first_commit": "2023-06-01",
                    "last_commit": "2024-01-10",
                },
            ],
            "total_commits": 100,
        }

        metadata = ingest_git_contributors(contributors_result)

        assert metadata["primary_author"] == "dev1@example.com"
        assert metadata["author_count"] == 2  # noqa: PLR2004
        assert "dev1@example.com" in metadata["authors"]
        assert "dev2@example.com" in metadata["authors"]
        assert metadata["source"] == "git_contributors"

    def test_handles_blame_format(self) -> None:
        """Test that it handles git_blame_summary output."""
        blame_result = {
            "status": "success",
            "authors": [
                {"email": "author@example.com", "lines": 100, "percentage": 80.0},
            ],
            "total_lines": 125,
        }

        metadata = ingest_git_contributors(blame_result)

        assert metadata["primary_author"] == "author@example.com"
        assert metadata["source"] == "git_blame"

    def test_handles_error_status(self) -> None:
        """Test that it returns empty dict on error."""
        error_result = {"status": "error", "error": "git not found"}

        metadata = ingest_git_contributors(error_result)

        assert metadata == {}

    def test_handles_empty_contributors(self) -> None:
        """Test that it handles empty contributors list."""
        result = {"status": "success", "contributors": [], "total_commits": 0}

        metadata = ingest_git_contributors(result)

        assert metadata == {}

    def test_limits_authors_to_top_5(self) -> None:
        """Test that it only includes top 5 authors."""
        contributors_result = {
            "status": "success",
            "contributors": [{"email": f"dev{i}@example.com", "commits": 10 - i} for i in range(10)],
        }

        metadata = ingest_git_contributors(contributors_result)

        assert len(metadata["authors"]) == 5  # noqa: PLR2004
        assert metadata["author_count"] == 10  # noqa: PLR2004
