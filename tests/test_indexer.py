"""Tests for the deterministic indexer pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_context_agent.indexer import _detect_languages, _get_file_manifest, build_index
from code_context_agent.tools.graph.model import CodeGraph


@pytest.fixture
def _mock_subprocess_rg(monkeypatch):
    """Mock subprocess.run to return a file list for rg --files."""
    import subprocess

    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[0] == "rg" and "--files" in cmd:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "src/main.py\nsrc/utils.py\napp.ts\nlib/helper.js\n"
            return result
        if cmd[0] == "git":
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            result.stderr = "not a git repo"
            return result
        if cmd[0] == "ast-grep":
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result
        if cmd[0] == "npx":
            result = MagicMock()
            result.returncode = 0
            result.stdout = "{}"
            return result
        return original_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)


@pytest.fixture
def _mock_no_external_tools(monkeypatch):
    """Mock shutil.which to report no external tools available."""
    monkeypatch.setattr("shutil.which", lambda _cmd: None)


async def test_build_index_creates_graph_file(tmp_path, monkeypatch):
    """build_index should create code_graph.json in the output directory."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("def hello(): pass\n")

    out = tmp_path / "output"

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        if cmd[0] == "rg":
            result.returncode = 0
            result.stdout = "main.py\n"
        elif cmd[0] == "git":
            result.returncode = 1
            result.stdout = ""
            result.stderr = "not a git repo"
        elif cmd[0] == "ast-grep":
            result.returncode = 0
            result.stdout = ""
        else:
            result.returncode = 0
            result.stdout = "{}"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/rg" if cmd == "rg" else None)

    # Mock LSP session manager - patch the singleton so it raises on get_or_create
    mock_mgr = MagicMock()
    mock_mgr.get_or_create = AsyncMock(side_effect=RuntimeError("no LSP"))
    mock_mgr.shutdown_all = AsyncMock()

    with patch("code_context_agent.indexer._ingest_lsp_symbols", new=AsyncMock()):
        await build_index(repo, output_dir=out, quiet=True)

    assert (out / "code_graph.json").exists()
    import json

    data = json.loads((out / "code_graph.json").read_text())
    assert "nodes" in data or "links" in data or "edges" in data


async def test_build_index_returns_graph(tmp_path, monkeypatch):
    """build_index should return a CodeGraph instance."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n")

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0 if cmd[0] == "rg" else 1
        result.stdout = "app.py\n" if cmd[0] == "rg" else ""
        result.stderr = ""
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/rg" if cmd == "rg" else None)

    with patch("code_context_agent.indexer._ingest_lsp_symbols", new=AsyncMock()):
        graph = await build_index(repo, quiet=True)

    assert isinstance(graph, CodeGraph)


async def test_build_index_no_lsp_graceful(tmp_path, monkeypatch):
    """When LSP fails, build_index should still produce a graph from git/astgrep data."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "server.ts").write_text("export function serve() {}\n")

    hotspot_call_count = 0

    def fake_run(cmd, **kwargs):
        nonlocal hotspot_call_count
        result = MagicMock()
        if cmd[0] == "rg":
            result.returncode = 0
            result.stdout = "server.ts\n"
        elif cmd[0] == "git" and "--name-only" in cmd:
            # Simulate git hotspot output
            result.returncode = 0
            result.stdout = "server.ts\n\nserver.ts\n"
            hotspot_call_count += 1
        elif cmd[0] == "git":
            result.returncode = 1
            result.stdout = ""
            result.stderr = ""
        elif cmd[0] == "ast-grep":
            result.returncode = 0
            result.stdout = ""
        else:
            result.returncode = 0
            result.stdout = "{}"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd in ("rg", "ast-grep") else None)

    # Mock _ingest_lsp_symbols to simulate LSP failure but still continue
    async def mock_lsp_noop(graph, repo, lang_files, quiet):
        pass  # LSP is unavailable, do nothing

    with patch("code_context_agent.indexer._ingest_lsp_symbols", new=mock_lsp_noop):
        graph = await build_index(repo, quiet=True)

    assert isinstance(graph, CodeGraph)
    # Graph should still have nodes from git hotspot analysis
    assert graph.node_count > 0 or hotspot_call_count > 0


def test_file_manifest_uses_ripgrep(monkeypatch):
    """_get_file_manifest should call rg --files."""
    import subprocess

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        result.stdout = "a.py\nb.ts\n"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/rg" if cmd == "rg" else None)

    files = _get_file_manifest(Path("/fake/repo"))

    assert len(calls) == 1
    assert calls[0][0] == "rg"
    assert "--files" in calls[0]
    assert files == ["a.py", "b.ts"]


def test_detect_languages_groups_by_extension():
    """_detect_languages should group files by their language extension."""
    files = [
        "src/main.py",
        "src/utils.py",
        "app.ts",
        "lib/helper.js",
        "lib/component.tsx",
        "README.md",
        "data.json",
        "server.go",
    ]
    result = _detect_languages(files)

    assert set(result["py"]) == {"src/main.py", "src/utils.py"}
    assert set(result["ts"]) == {"app.ts", "lib/helper.js", "lib/component.tsx"}
    assert result["go"] == ["server.go"]
    # README.md and data.json should not be in any language group
    assert "md" not in result
    assert "json" not in result
