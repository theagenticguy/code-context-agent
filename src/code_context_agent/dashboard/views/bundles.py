"""Bundles view: multi-area markdown viewer with tabs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import panel as pn

    from .._data import DashboardData


def build_bundles_view(data: DashboardData) -> pn.viewable.Viewable:
    """Build the bundles tab with one tab per bundle area.

    Each BUNDLE.*.md file is rendered in its own tab with Mermaid diagram
    support. Tab titles are the area names with the first letter capitalized.
    """
    import panel as pn

    from .._mermaid import render_markdown_with_mermaid

    if not data.bundles:
        return pn.pane.HTML(
            '<div style="color:#888;padding:2rem;text-align:center;font-size:1rem">'
            "No bundle files found. Run <code>code-context-agent analyze</code> to generate bundles."
            "</div>",
            sizing_mode="stretch_width",
        )

    tabs_list: list[tuple[str, pn.viewable.Viewable]] = []

    for area_name, content in data.bundles.items():
        title = area_name.replace("-", " ").replace("_", " ").title()

        if not content.strip():
            tab_content = pn.pane.HTML(
                f'<div style="color:#888;padding:1rem">No content for {title}.</div>',
                sizing_mode="stretch_width",
            )
        else:
            panes = render_markdown_with_mermaid(content)
            tab_content = pn.Column(
                *panes,
                sizing_mode="stretch_width",
                scroll=True,
                styles={"max-height": "800px", "padding": "0.5rem"},
            )

        tabs_list.append((title, tab_content))

    tabs = pn.Tabs(*tabs_list, dynamic=True, sizing_mode="stretch_width")

    return pn.Column(tabs, sizing_mode="stretch_width")
