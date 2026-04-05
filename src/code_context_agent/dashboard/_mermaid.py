"""Mermaid diagram rendering via Panel JSComponent with vendored mermaid.min.js."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import param

if TYPE_CHECKING:
    import panel as pn

# Path to the vendored mermaid.min.js (populated by `mise run viz:fetch-mermaid`)
_VENDOR_DIR = Path(__file__).parent / "_vendor"
_MERMAID_JS = _VENDOR_DIR / "mermaid.min.js"


def _get_mermaid_js_url() -> str:
    """Get the URL or path to mermaid.min.js.

    Returns the local vendored path if available, with a fallback warning.
    """
    if _MERMAID_JS.exists():
        return "/static/vendor/mermaid.min.js"
    msg = "Vendored mermaid.min.js not found. Run 'mise run viz:fetch-mermaid' to download it."
    raise FileNotFoundError(msg)


class MermaidDiagram(param.Parameterized):
    """Renders a Mermaid diagram string as an SVG via Panel HTML pane."""

    value = param.String(default="", doc="Mermaid diagram source code")

    def panel(self) -> pn.pane.HTML:
        """Return a Panel HTML pane that renders the Mermaid diagram."""
        import panel as pn

        if not self.value.strip():
            return pn.pane.HTML("")

        # Use inline script with the vendored mermaid.min.js served via static_dirs
        mermaid_url = _get_mermaid_js_url()
        unique_id = f"mermaid-{id(self)}"
        html = f"""
        <div id="{unique_id}" style="background: transparent; padding: 1rem;">
            <pre class="mermaid">{self.value}</pre>
        </div>
        <script type="module">
            import mermaid from '{mermaid_url}';
            mermaid.initialize({{ startOnLoad: true, theme: 'dark', securityLevel: 'loose' }});
            await mermaid.run({{ nodes: document.querySelectorAll('#{unique_id} .mermaid') }});
        </script>
        """
        return pn.pane.HTML(html, sizing_mode="stretch_width", min_height=200)


def extract_mermaid_blocks(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into alternating (text, mermaid) segments.

    Args:
        markdown: Raw markdown text potentially containing ```mermaid blocks.

    Returns:
        List of (type, content) tuples where type is 'markdown' or 'mermaid'.
    """
    pattern = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
    segments: list[tuple[str, str]] = []
    last_end = 0

    for match in pattern.finditer(markdown):
        # Text before this mermaid block
        before = markdown[last_end : match.start()].strip()
        if before:
            segments.append(("markdown", before))
        segments.append(("mermaid", match.group(1).strip()))
        last_end = match.end()

    # Remaining text after last mermaid block
    after = markdown[last_end:].strip()
    if after:
        segments.append(("markdown", after))

    if not segments and markdown.strip():
        segments.append(("markdown", markdown))

    return segments


def render_markdown_with_mermaid(markdown: str) -> list:
    """Render markdown content, replacing mermaid blocks with diagram panes.

    Args:
        markdown: Raw markdown text.

    Returns:
        List of Panel panes (Markdown and HTML for mermaid diagrams).
    """
    import panel as pn

    segments = extract_mermaid_blocks(markdown)
    panes = []

    for seg_type, content in segments:
        if seg_type == "mermaid":
            diagram = MermaidDiagram(value=content)
            panes.append(diagram.panel())
        else:
            panes.append(pn.pane.Markdown(content, sizing_mode="stretch_width"))

    return panes
