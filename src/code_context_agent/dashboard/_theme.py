"""Shared theme configuration: Altair dark theme and color constants."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Node type colors (ported from ui/src/constants/colors.ts)
# ---------------------------------------------------------------------------
NODE_COLORS: dict[str, str] = {
    "file": "#60a5fa",
    "class": "#a78bfa",
    "function": "#34d399",
    "method": "#22d3ee",
    "variable": "#fbbf24",
    "module": "#f472b6",
    "pattern_match": "#fb923c",
    "unknown": "#6a6a86",
}

EDGE_COLORS: dict[str, str] = {
    "calls": "#c4b5fd",
    "imports": "#93c5fd",
    "references": "#a1a1aa",
    "contains": "#71717a",
    "inherits": "#d8b4fe",
    "implements": "#67e8f9",
    "tests": "#6ee7b7",
    "cochanges": "#fde68a",
    "similar_to": "#fb923c",
    "unknown": "#52525b",
}

SEVERITY_COLORS: dict[str, str] = {
    "critical": "#ef4444",
    "high": "#f87171",
    "medium": "#fbbf24",
    "low": "#4ade80",
}

FALLBACK_COLOR = "#6a6a86"

# Ordered palettes for Altair scale domains
NODE_TYPE_ORDER = ["file", "class", "function", "method", "variable", "module", "pattern_match"]
EDGE_TYPE_ORDER = [
    "calls",
    "imports",
    "references",
    "contains",
    "inherits",
    "implements",
    "tests",
    "cochanges",
    "similar_to",
]


def apply_theme() -> None:
    """Register and enable the Code Context dark theme for Altair."""
    import altair as alt

    @alt.theme.register("code_context_dark", enable=True)
    def _code_context_dark() -> alt.theme.ThemeConfig:
        return {
            "config": {
                "background": "#1a1a2e",
                "view": {"continuousWidth": 400, "continuousHeight": 300, "stroke": "transparent"},
                "axis": {
                    "domainColor": "#444",
                    "gridColor": "#2a2a3e",
                    "tickColor": "#444",
                    "labelColor": "#ccc",
                    "titleColor": "#eee",
                    "labelFont": "system-ui, sans-serif",
                    "titleFont": "system-ui, sans-serif",
                },
                "legend": {"labelColor": "#ccc", "titleColor": "#eee"},
                "title": {"color": "#eee", "font": "system-ui, sans-serif"},
                "mark": {"color": "#7C3AED"},
                "range": {
                    "category": list(NODE_COLORS.values()),
                },
            },
        }

    alt.data_transformers.disable_max_rows()
