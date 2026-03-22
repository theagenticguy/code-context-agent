"""Tests for the multi-repo MCP registry."""

from __future__ import annotations

import pytest

from code_context_agent.config import DEFAULT_OUTPUT_DIR
from code_context_agent.mcp.registry import Registry


@pytest.fixture
def registry(tmp_path):
    """Create a Registry backed by a temp file."""
    return Registry(registry_path=tmp_path / "registry.json")


@pytest.fixture
def fake_repo(tmp_path):
    """Create a fake repo directory with no artifacts."""
    repo = tmp_path / "my-repo"
    repo.mkdir()
    return repo


@pytest.fixture
def fake_repo_with_graph(tmp_path):
    """Create a fake repo with a code_graph.json artifact."""
    repo = tmp_path / "graphed-repo"
    repo.mkdir()
    output_dir = repo / DEFAULT_OUTPUT_DIR
    output_dir.mkdir()
    (output_dir / "code_graph.json").write_text("{}")
    (output_dir / "CONTEXT.md").write_text("# Context")
    return repo


def test_register_creates_entry(registry, fake_repo):
    entry = registry.register("myrepo", str(fake_repo))
    assert entry.alias == "myrepo"
    assert entry.path == str(fake_repo.resolve())
    repos = registry.list_repos()
    assert len(repos) == 1
    assert repos[0]["alias"] == "myrepo"


def test_register_detects_graph(registry, fake_repo_with_graph):
    entry = registry.register("graphed", str(fake_repo_with_graph))
    assert entry.graph_exists is True
    assert entry.artifact_count == 2  # noqa: PLR2004


def test_unregister_removes_entry(registry, fake_repo):
    registry.register("myrepo", str(fake_repo))
    assert registry.unregister("myrepo") is True
    assert registry.list_repos() == []


def test_unregister_nonexistent_returns_false(registry):
    assert registry.unregister("nonexistent") is False


def test_list_repos_empty(registry):
    assert registry.list_repos() == []


def test_find_by_path_exact_match(registry, fake_repo):
    registry.register("myrepo", str(fake_repo))
    alias = registry.find_by_path(str(fake_repo))
    assert alias == "myrepo"


def test_find_by_path_not_found(registry):
    assert registry.find_by_path("/does/not/exist") is None


def test_load_graph_returns_none_for_missing(registry):
    assert registry.load_graph("nonexistent") is None
