from __future__ import annotations

from pathlib import Path

VIZ_DIR = Path(__file__).resolve().parent.parent / "src" / "code_context_agent" / "viz"
INDEX_HTML = VIZ_DIR / "index.html"


def test_viz_index_html_exists() -> None:
    """Verify the viz index.html file exists at the expected package path."""
    assert INDEX_HTML.exists(), f"Expected {INDEX_HTML} to exist"
    assert INDEX_HTML.stat().st_size > 0, "index.html should not be empty"


def test_viz_html_contains_d3_import() -> None:
    """Verify the HTML references d3.js from CDN."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert "d3js.org/d3.v7" in content or "d3.v7.min.js" in content, "index.html should reference D3.js v7 from CDN"


def test_viz_html_contains_graph_fetch() -> None:
    """Verify the HTML fetches code_graph.json."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert "code_graph.json" in content, "index.html should fetch code_graph.json"


def test_viz_html_has_controls() -> None:
    """Verify the HTML has filter controls for edge types and search."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert "edge-type" in content.lower() or "edgetype" in content.lower(), (
        "index.html should have edge type filter controls"
    )
    assert "search" in content.lower(), "index.html should have a search control"
    assert "node-type" in content.lower() or "nodetype" in content.lower(), (
        "index.html should have node type filter controls"
    )
