from __future__ import annotations

from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "src" / "code_context_agent" / "ui"
INDEX_HTML = UI_DIR / "index.html"


def test_viz_index_html_exists() -> None:
    """Verify the viz index.html file exists at the expected path."""
    assert INDEX_HTML.exists(), f"Expected {INDEX_HTML} to exist"
    assert INDEX_HTML.stat().st_size > 0, "index.html should not be empty"


def test_viz_html_contains_d3_import() -> None:
    """Verify the HTML references D3.js v7 from CDN."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert "d3@7" in content or "d3.v7" in content, "index.html should reference D3.js v7 from CDN"


def test_viz_html_contains_tailwind() -> None:
    """Verify the HTML loads Tailwind CSS v4 from CDN."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert "tailwindcss" in content.lower(), "index.html should load Tailwind CSS"


def test_viz_has_app_js() -> None:
    """Verify the app.js entry point exists."""
    app_js = UI_DIR / "js" / "app.js"
    assert app_js.exists(), f"Expected {app_js} to exist"


def test_viz_has_views() -> None:
    """Verify all 10 view modules exist."""
    views_dir = UI_DIR / "js" / "views"
    expected_views = [
        "landing.js",
        "dashboard.js",
        "graph.js",
        "modules.js",
        "hotspots.js",
        "dependencies.js",
        "narrative.js",
        "bundles.js",
        "insights.js",
        "signatures.js",
    ]
    for view in expected_views:
        view_path = views_dir / view
        assert view_path.exists(), f"Expected view {view} at {view_path}"
