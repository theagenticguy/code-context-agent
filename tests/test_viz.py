from __future__ import annotations

from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parent.parent / "src" / "code_context_agent" / "ui"
INDEX_HTML = UI_DIR / "index.html"
ASSETS_DIR = UI_DIR / "assets"

_frontend_built = ASSETS_DIR.exists() and any(ASSETS_DIR.glob("*.js"))
needs_frontend_build = pytest.mark.skipif(
    not _frontend_built,
    reason="Frontend not built — run 'mise run ui:build' first",
)


@needs_frontend_build
def test_viz_index_html_exists() -> None:
    """Verify the viz index.html file exists at the expected path."""
    assert INDEX_HTML.exists(), f"Expected {INDEX_HTML} to exist"
    assert INDEX_HTML.stat().st_size > 0, "index.html should not be empty"


@needs_frontend_build
def test_viz_html_is_react_build() -> None:
    """Verify the HTML is a Vite-built React app."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert '<div id="root">' in content, "index.html should have React root element"
    assert "assets/" in content, "index.html should reference built assets"


@needs_frontend_build
def test_viz_has_built_assets() -> None:
    """Verify Vite build output includes JS and CSS bundles."""
    assert ASSETS_DIR.exists(), f"Expected {ASSETS_DIR} to exist"
    js_files = list(ASSETS_DIR.glob("*.js"))
    css_files = list(ASSETS_DIR.glob("*.css"))
    assert len(js_files) >= 1, "Should have at least one JS bundle"
    assert len(css_files) >= 1, "Should have at least one CSS bundle"
