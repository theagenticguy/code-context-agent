"""Tests for the Panel-based visualization dashboard."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_dashboard_module_importable() -> None:
    """Verify the dashboard package is importable."""
    from code_context_agent.dashboard import build_dashboard

    assert callable(build_dashboard)


def test_data_module_importable() -> None:
    """Verify the data loader is importable."""
    from code_context_agent.dashboard._data import DashboardData, load_dashboard_data

    assert callable(load_dashboard_data)
    assert DashboardData is not None


def test_theme_module_importable() -> None:
    """Verify theme constants are importable."""
    from code_context_agent.dashboard._theme import (
        EDGE_COLORS,
        FALLBACK_COLOR,
        NODE_COLORS,
        SEVERITY_COLORS,
    )

    assert len(NODE_COLORS) > 0
    assert len(EDGE_COLORS) > 0
    assert len(SEVERITY_COLORS) > 0
    assert isinstance(FALLBACK_COLOR, str)


def test_mermaid_extract_blocks() -> None:
    """Verify mermaid block extraction from markdown."""
    from code_context_agent.dashboard._mermaid import extract_mermaid_blocks

    md = "# Hello\n\n```mermaid\ngraph TD; A-->B;\n```\n\nMore text"
    segments = extract_mermaid_blocks(md)
    assert len(segments) == 3
    assert segments[0] == ("markdown", "# Hello")
    assert segments[1] == ("mermaid", "graph TD; A-->B;")
    assert segments[2] == ("markdown", "More text")


def test_mermaid_no_blocks() -> None:
    """Verify plain markdown returns single segment."""
    from code_context_agent.dashboard._mermaid import extract_mermaid_blocks

    segments = extract_mermaid_blocks("Just plain text")
    assert len(segments) == 1
    assert segments[0] == ("markdown", "Just plain text")


def test_load_dashboard_data_empty_dir(tmp_path: Path) -> None:
    """Verify loading from empty directory produces empty data."""
    from code_context_agent.dashboard._data import load_dashboard_data

    data = load_dashboard_data(tmp_path)
    assert data.graph is None
    assert data.analysis_result == {}
    assert data.narrative == ""
    assert data.bundles == {}
    assert data.signatures == ""


def test_load_dashboard_data_with_files(tmp_path: Path) -> None:
    """Verify loading real data files."""
    import json

    from code_context_agent.dashboard._data import load_dashboard_data

    # Create minimal analysis_result.json
    result = {"status": "completed", "summary": "Test", "total_files_analyzed": 10}
    (tmp_path / "analysis_result.json").write_text(json.dumps(result))

    # Create minimal narrative
    (tmp_path / "CONTEXT.md").write_text("# Test Narrative\n\nHello world")

    # Create bundle
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()
    (bundles_dir / "BUNDLE.auth.md").write_text("# Auth Bundle")

    data = load_dashboard_data(tmp_path)
    assert data.analysis_result["status"] == "completed"
    assert "Test Narrative" in data.narrative
    assert "auth" in data.bundles
    assert "Auth Bundle" in data.bundles["auth"]


def test_view_stubs_importable() -> None:
    """Verify all view modules are importable."""
    from code_context_agent.dashboard.views.bundles import build_bundles_view
    from code_context_agent.dashboard.views.dependencies import build_dependencies_view
    from code_context_agent.dashboard.views.graph import build_graph_view
    from code_context_agent.dashboard.views.hotspots import build_hotspots_view
    from code_context_agent.dashboard.views.insights import build_insights_view
    from code_context_agent.dashboard.views.modules import build_modules_view
    from code_context_agent.dashboard.views.narrative import build_narrative_view
    from code_context_agent.dashboard.views.overview import build_overview_view
    from code_context_agent.dashboard.views.signatures import build_signatures_view

    for fn in [
        build_bundles_view,
        build_dependencies_view,
        build_graph_view,
        build_hotspots_view,
        build_insights_view,
        build_modules_view,
        build_narrative_view,
        build_overview_view,
        build_signatures_view,
    ]:
        assert callable(fn)
