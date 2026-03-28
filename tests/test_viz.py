from __future__ import annotations

from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "src" / "code_context_agent" / "ui"
INDEX_HTML = UI_DIR / "index.html"


def test_viz_index_html_exists() -> None:
    """Verify the viz index.html file exists at the expected path."""
    assert INDEX_HTML.exists(), f"Expected {INDEX_HTML} to exist"
    assert INDEX_HTML.stat().st_size > 0, "index.html should not be empty"


def test_viz_html_is_react_build() -> None:
    """Verify the HTML is a Vite-built React app."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert '<div id="root">' in content, "index.html should have React root element"
    assert "assets/" in content, "index.html should reference built assets"


def test_viz_has_built_assets() -> None:
    """Verify Vite build output includes JS and CSS bundles."""
    assets_dir = UI_DIR / "assets"
    assert assets_dir.exists(), f"Expected {assets_dir} to exist"
    js_files = list(assets_dir.glob("*.js"))
    css_files = list(assets_dir.glob("*.css"))
    assert len(js_files) >= 1, "Should have at least one JS bundle"
    assert len(css_files) >= 1, "Should have at least one CSS bundle"
