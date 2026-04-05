"""Panel-based interactive dashboard for code analysis visualization."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from panel.template import FastListTemplate


def build_dashboard(agent_dir: Path) -> FastListTemplate:
    """Build the complete dashboard from analysis artifacts.

    Args:
        agent_dir: Path to the .code-context/ output directory.

    Returns:
        A Panel Viewable (FastListTemplate) ready for serving.
    """
    import panel as pn

    from ._data import load_dashboard_data
    from ._theme import apply_theme

    apply_theme()

    data = load_dashboard_data(agent_dir)

    # Import views
    from .views.bundles import build_bundles_view
    from .views.dependencies import build_dependencies_view
    from .views.graph import build_graph_view
    from .views.hotspots import build_hotspots_view
    from .views.insights import build_insights_view
    from .views.modules import build_modules_view
    from .views.narrative import build_narrative_view
    from .views.overview import build_overview_view
    from .views.signatures import build_signatures_view

    # Build all views
    overview = build_overview_view(data)
    graph = build_graph_view(data)
    modules = build_modules_view(data)
    hotspots = build_hotspots_view(data)
    deps = build_dependencies_view(data)
    narrative = build_narrative_view(data)
    bundles = build_bundles_view(data)
    insights = build_insights_view(data)
    signatures = build_signatures_view(data)

    # Assemble template
    template = pn.template.FastListTemplate(
        title="Code Context Agent",
        site="CCA",
        theme="dark",
        accent_base_color="#7C3AED",
        header_background="#0f0f0f",
        sidebar_width=220,
        main_max_width="1600px",
        theme_toggle=False,
    )

    tabs = pn.Tabs(
        ("Overview", overview),
        ("Graph", graph),
        ("Modules", modules),
        ("Hotspots", hotspots),
        ("Dependencies", deps),
        ("Narrative", narrative),
        ("Bundles", bundles),
        ("Insights", insights),
        ("Signatures", signatures),
        dynamic=True,
        tabs_location="above",
    )

    template.main.append(tabs)

    return template
