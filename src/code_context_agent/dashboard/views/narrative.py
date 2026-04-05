"""Narrative view: rendered CONTEXT.md with Mermaid support and TOC sidebar."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import panel as pn

    from .._data import DashboardData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_headings(markdown: str) -> list[tuple[int, str, str]]:
    """Parse ## and ### headings into (level, title, slug) tuples.

    Args:
        markdown: Raw markdown text.

    Returns:
        List of (heading_level, title_text, url_slug) tuples.
    """
    headings: list[tuple[int, str, str]] = []
    for match in re.finditer(r"^(#{2,3})\s+(.+)$", markdown, re.MULTILINE):
        level = len(match.group(1))
        title = match.group(2).strip()
        slug = re.sub(r"[^\w\s-]", "", title.lower()).replace(" ", "-")
        headings.append((level, title, slug))
    return headings


def _build_toc_html(headings: list[tuple[int, str, str]]) -> str:
    """Build an HTML table-of-contents sidebar from parsed headings.

    Args:
        headings: Output of ``_extract_headings``.

    Returns:
        Styled HTML string with anchor links.
    """
    if not headings:
        return '<div style="color:#888;padding:1rem;font-size:0.85rem">No headings found.</div>'

    lines: list[str] = []
    for level, title, slug in headings:
        indent = (level - 2) * 16  # 0px for ##, 16px for ###
        color = "#a78bfa" if level == 2 else "#ccc"
        weight = "600" if level == 2 else "400"
        size = "0.85rem" if level == 2 else "0.8rem"
        lines.append(
            f'<a href="#{slug}" style="display:block;padding:4px 0 4px {indent}px;'
            f"color:{color};font-weight:{weight};font-size:{size};"
            f'text-decoration:none;line-height:1.5" '
            f"onmouseover=\"this.style.color='#c4b5fd'\" "
            f"onmouseout=\"this.style.color='{color}'\">"
            f"{title}</a>",
        )

    return (
        '<div style="padding:0.75rem 1rem">'
        '<div style="color:#aaa;font-size:0.75rem;text-transform:uppercase;'
        'letter-spacing:0.05em;margin-bottom:0.5rem;font-weight:600">Table of Contents</div>'
        + "\n".join(lines)
        + "</div>"
    )


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_narrative_view(data: DashboardData) -> pn.viewable.Viewable:
    """Build the narrative tab with a TOC sidebar and rendered content.

    Renders CONTEXT.md with Mermaid diagram support. A left sidebar provides
    a clickable table of contents parsed from ## and ### headings.
    """
    import panel as pn

    from .._mermaid import render_markdown_with_mermaid

    if not data.narrative.strip():
        return pn.pane.HTML(
            '<div style="color:#888;padding:2rem;text-align:center;font-size:1rem">'
            "No narrative content. Run <code>code-context-agent analyze</code> first."
            "</div>",
            sizing_mode="stretch_width",
        )

    # Build TOC sidebar
    headings = _extract_headings(data.narrative)
    toc_html = _build_toc_html(headings)
    toc_sidebar = pn.pane.HTML(
        toc_html,
        sizing_mode="fixed",
        width=250,
        styles={
            "background": "#1a1a2e",
            "border-right": "1px solid #2a2a3e",
            "overflow-y": "auto",
        },
    )

    # Build content area
    panes = render_markdown_with_mermaid(data.narrative)
    content = pn.Column(
        *panes,
        sizing_mode="stretch_width",
        scroll=True,
        styles={"max-height": "800px", "padding": "0 1rem"},
    )

    return pn.Row(
        toc_sidebar,
        content,
        sizing_mode="stretch_width",
    )
