"""Signatures view: searchable markdown with heading filter."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import panel as pn

    from .._data import DashboardData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sections(markdown: str) -> list[tuple[str, str]]:
    """Split signatures markdown into sections by ## headings.

    Args:
        markdown: Raw markdown text organized by ``## Heading`` blocks.

    Returns:
        List of (heading, content_body) tuples.
    """
    sections: list[tuple[str, str]] = []
    parts = re.split(r"^(## .+)$", markdown, flags=re.MULTILINE)
    # Split produces: preamble, heading, content, heading, content, ...
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections.append((heading, content))
    return sections


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_signatures_view(data: DashboardData) -> pn.viewable.Viewable:
    """Build the signatures tab with a search filter.

    Parses CONTEXT.signatures.md into sections by ``##`` headings and
    provides a text input that reactively filters sections by heading
    or content (case-insensitive).
    """
    import panel as pn

    if not data.signatures.strip():
        return pn.pane.HTML(
            '<div style="color:#888;padding:2rem;text-align:center;font-size:1rem">'
            "No signatures content. Run <code>code-context-agent analyze</code> first."
            "</div>",
            sizing_mode="stretch_width",
        )

    sections = _parse_sections(data.signatures)

    if not sections:
        # Signatures file exists but has no ## headings; render as plain markdown
        return pn.pane.Markdown(data.signatures, sizing_mode="stretch_width")

    search_widget = pn.widgets.TextInput(
        placeholder="Filter by heading or content...",
        sizing_mode="stretch_width",
        styles={"max-width": "500px"},
    )

    def _filter_sections(search: str) -> pn.viewable.Viewable:
        """Return a Column of markdown panes filtered by the search term."""
        query = (search or "").strip().lower()
        panes: list[pn.pane.Markdown] = []

        for heading, content in sections:
            if query and query not in heading.lower() and query not in content.lower():
                continue
            md_text = f"{heading}\n\n{content}" if content else heading
            panes.append(pn.pane.Markdown(md_text, sizing_mode="stretch_width"))

        if not panes:
            return pn.pane.HTML(
                f'<div style="color:#888;padding:1rem;font-size:0.9rem">No sections match "<b>{search}</b>".</div>',
                sizing_mode="stretch_width",
            )

        return pn.Column(*panes, sizing_mode="stretch_width")

    filtered_output = pn.bind(_filter_sections, search=search_widget)

    count_label = pn.pane.HTML(
        f'<div style="color:#888;font-size:0.8rem;margin-bottom:0.5rem">'
        f"{len(sections)} signature section{'s' if len(sections) != 1 else ''} loaded</div>",
        sizing_mode="stretch_width",
    )

    return pn.Column(
        count_label,
        search_widget,
        filtered_output,
        sizing_mode="stretch_width",
    )
