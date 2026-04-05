"""Overview dashboard view: KPI cards, distribution charts, code health."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import panel as pn

    from .._data import DashboardData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kpi_card(title: str, value: str, subtitle: str = "") -> str:
    """Return styled HTML for a single KPI card."""
    sub_html = f'<div style="color:#888;font-size:0.8rem;margin-top:4px">{subtitle}</div>' if subtitle else ""
    return (
        '<div style="background:#1e1e2e;border-radius:8px;padding:1.5rem;'
        'text-align:center;min-width:160px;flex:1">'
        f'<div style="color:#aaa;font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em">{title}</div>'
        f'<div style="color:#eee;font-size:2rem;font-weight:700;margin-top:0.3rem">{value}</div>'
        f"{sub_html}"
        "</div>"
    )


def _no_data(label: str) -> str:
    """Placeholder markdown when a section has no data."""
    return f"*No {label} data available.*"


def _safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Nested dict access that never raises."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------


def _node_type_chart(nodes: list[dict[str, Any]], *, precomputed_counts: list[dict[str, Any]] | None = None) -> Any:
    """Horizontal bar chart of node-type counts.

    Args:
        nodes: Raw node dicts (used as fallback when *precomputed_counts* is None).
        precomputed_counts: Pre-aggregated list of ``{"node_type": str, "count": int}`` dicts
            from ``DashboardCache.node_type_counts``.  When provided, *nodes* is ignored.
    """
    import altair as alt

    from .._theme import FALLBACK_COLOR, NODE_COLORS, NODE_TYPE_ORDER

    if precomputed_counts is not None:
        counts = {r["node_type"]: r["count"] for r in precomputed_counts}
    else:
        counts = {}
        for n in nodes:
            nt = n.get("node_type", "unknown")
            counts[nt] = counts.get(nt, 0) + 1

    if not counts:
        return None

    records = [{"node_type": k, "count": v} for k, v in counts.items()]

    domain = [t for t in NODE_TYPE_ORDER if t in counts] + [t for t in counts if t not in NODE_TYPE_ORDER]
    range_ = [NODE_COLORS.get(t, FALLBACK_COLOR) for t in domain]

    chart = (
        alt.Chart(alt.Data(values=records))
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y("node_type:N", sort="-x", title="Node Type"),
            x=alt.X("count:Q", title="Count"),
            color=alt.Color(
                "node_type:N",
                scale=alt.Scale(domain=domain, range=range_),
                legend=None,
            ),
            tooltip=["node_type:N", "count:Q"],
        )
        .properties(width="container", height=max(len(counts) * 28, 120), title="Node Type Distribution")
    )
    return chart


def _edge_type_chart(links: list[dict[str, Any]], *, precomputed_counts: list[dict[str, Any]] | None = None) -> Any:
    """Horizontal bar chart of edge-type counts.

    Args:
        links: Raw edge/link dicts (used as fallback when *precomputed_counts* is None).
        precomputed_counts: Pre-aggregated list of ``{"edge_type": str, "count": int}`` dicts
            from ``DashboardCache.edge_type_counts``.  When provided, *links* is ignored.
    """
    import altair as alt

    from .._theme import EDGE_COLORS, EDGE_TYPE_ORDER, FALLBACK_COLOR

    if precomputed_counts is not None:
        counts = {r["edge_type"]: r["count"] for r in precomputed_counts}
    else:
        counts = {}
        for e in links:
            et = e.get("edge_type", "unknown")
            counts[et] = counts.get(et, 0) + 1

    if not counts:
        return None

    records = [{"edge_type": k, "count": v} for k, v in counts.items()]

    domain = [t for t in EDGE_TYPE_ORDER if t in counts] + [t for t in counts if t not in EDGE_TYPE_ORDER]
    range_ = [EDGE_COLORS.get(t, FALLBACK_COLOR) for t in domain]

    chart = (
        alt.Chart(alt.Data(values=records))
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y("edge_type:N", sort="-x", title="Edge Type"),
            x=alt.X("count:Q", title="Count"),
            color=alt.Color(
                "edge_type:N",
                scale=alt.Scale(domain=domain, range=range_),
                legend=None,
            ),
            tooltip=["edge_type:N", "count:Q"],
        )
        .properties(width="container", height=max(len(counts) * 28, 120), title="Edge Type Distribution")
    )
    return chart


def _risk_chart(risks: list[dict[str, Any]]) -> Any:
    """Horizontal bar chart of risk counts by severity."""
    import altair as alt

    from .._theme import FALLBACK_COLOR, SEVERITY_COLORS

    counts: dict[str, int] = {}
    for r in risks:
        sev = (r.get("severity") or "unknown").lower()
        counts[sev] = counts.get(sev, 0) + 1

    if not counts:
        return None

    records = [{"severity": k, "count": v} for k, v in counts.items()]

    severity_order = ["critical", "high", "medium", "low"]
    domain = [s for s in severity_order if s in counts] + [s for s in counts if s not in severity_order]
    range_ = [SEVERITY_COLORS.get(s, FALLBACK_COLOR) for s in domain]

    chart = (
        alt.Chart(alt.Data(values=records))
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y("severity:N", sort=domain, title="Severity"),
            x=alt.X("count:Q", title="Count"),
            color=alt.Color(
                "severity:N",
                scale=alt.Scale(domain=domain, range=range_),
                legend=None,
            ),
            tooltip=["severity:N", "count:Q"],
        )
        .properties(width="container", height=max(len(counts) * 36, 100), title="Risk Summary")
    )
    return chart


def _business_logic_table(items: list[dict[str, Any]]) -> str:
    """HTML table for top-10 business logic items."""
    top = sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:10]
    if not top:
        return _no_data("business logic")

    rows = ""
    for it in top:
        loc = (it.get("location") or "").replace("<", "&lt;").replace(">", "&gt;")
        name = (it.get("name") or "").replace("<", "&lt;").replace(">", "&gt;")
        role = (it.get("role") or "").replace("<", "&lt;").replace(">", "&gt;")
        cat = (it.get("category") or "-").replace("<", "&lt;").replace(">", "&gt;")
        score = it.get("score", 0)
        rank = it.get("rank", "-")
        rows += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #2a2a3e'>{rank}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #2a2a3e;color:#a78bfa;font-weight:600'>{name}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #2a2a3e'>{role}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #2a2a3e;font-family:monospace;font-size:0.8rem'>"
            f"{loc}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #2a2a3e;text-align:right'>{score:.2f}</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #2a2a3e'>{cat}</td>"
            f"</tr>"
        )

    header_style = (
        "padding:8px 10px;border-bottom:2px solid #444;color:#aaa;"
        "text-transform:uppercase;font-size:0.75rem;letter-spacing:0.05em"
    )
    return (
        '<div style="overflow-x:auto">'
        '<table style="width:100%;border-collapse:collapse;color:#ddd;font-size:0.85rem">'
        f"<thead><tr>"
        f"<th style='{header_style}'>Rank</th>"
        f"<th style='{header_style}'>Name</th>"
        f"<th style='{header_style}'>Role</th>"
        f"<th style='{header_style}'>Location</th>"
        f"<th style='{header_style};text-align:right'>Score</th>"
        f"<th style='{header_style}'>Category</th>"
        f"</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
    )


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_overview_view(data: DashboardData) -> pn.viewable.Viewable:
    """Build the overview dashboard tab.

    Contains a summary header, KPI cards, node/edge/risk distribution charts,
    and a top-10 business logic table.
    """
    import panel as pn

    ar = data.analysis_result
    hs = data.heuristic_summary
    gr = data.graph_raw

    sections: list[Any] = []

    # ---- 1. Summary header ----
    summary = ar.get("summary")
    mode = ar.get("analysis_mode", "standard")
    if summary:
        badge_color = "#7C3AED" if mode == "standard" else "#2563eb"
        badge = (
            f'<span style="background:{badge_color};color:#fff;padding:2px 10px;'
            f'border-radius:12px;font-size:0.75rem;margin-left:8px">{mode}</span>'
        )
        sections.append(
            pn.pane.HTML(
                f'<div style="margin-bottom:0.5rem"><h2 style="color:#eee;display:inline">Overview</h2>{badge}</div>'
                f'<p style="color:#ccc;font-size:0.95rem;line-height:1.6">{summary}</p>',
                sizing_mode="stretch_width",
            ),
        )
    else:
        sections.append(pn.pane.Markdown("## Overview", sizing_mode="stretch_width"))

    # ---- 2. KPI stat row ----
    total_files = ar.get("total_files_analyzed") or _safe_get(hs, "volume", "total_files", default=0)
    graph_stats = ar.get("graph_stats") or {}
    node_count = graph_stats.get("node_count") or len(gr.get("nodes", []))
    edge_count = graph_stats.get("edge_count") or len(gr.get("links", []))

    code_health = ar.get("code_health") or {}
    dup_pct = code_health.get("duplication_percentage", 0)
    smell_count = code_health.get("code_smell_count", 0)
    health_score = max(0, min(100, round(100 - (dup_pct + smell_count * 2))))

    health_color = "#4ade80" if health_score >= 75 else ("#fbbf24" if health_score >= 50 else "#ef4444")

    cards_html = (
        '<div style="display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0">'
        + _kpi_card("Files Analyzed", f"{total_files:,}")
        + _kpi_card("Graph Nodes", f"{node_count:,}")
        + _kpi_card("Graph Edges", f"{edge_count:,}")
        + _kpi_card("Code Health", f'<span style="color:{health_color}">{health_score}</span>', subtitle="/100")
        + "</div>"
    )
    sections.append(pn.pane.HTML(cards_html, sizing_mode="stretch_width"))

    # ---- 3. Node type distribution ----
    cached_node_counts = data.cache.node_type_counts.to_dicts() if data.cache.node_type_counts is not None else None
    nodes = gr.get("nodes", [])
    if cached_node_counts or nodes:
        chart = _node_type_chart(nodes, precomputed_counts=cached_node_counts)
        if chart is not None:
            sections.append(pn.pane.Vega(chart, sizing_mode="stretch_width"))
    else:
        sections.append(pn.pane.Markdown(_no_data("node type distribution")))

    # ---- 4. Edge type distribution ----
    cached_edge_counts = data.cache.edge_type_counts.to_dicts() if data.cache.edge_type_counts is not None else None
    links = gr.get("links", [])
    if cached_edge_counts or links:
        chart = _edge_type_chart(links, precomputed_counts=cached_edge_counts)
        if chart is not None:
            sections.append(pn.pane.Vega(chart, sizing_mode="stretch_width"))
    else:
        sections.append(pn.pane.Markdown(_no_data("edge type distribution")))

    # ---- 5. Risk summary ----
    risks = ar.get("risks", [])
    if risks:
        chart = _risk_chart(risks)
        if chart is not None:
            sections.append(pn.pane.Vega(chart, sizing_mode="stretch_width"))
    else:
        sections.append(pn.pane.Markdown(_no_data("risk")))

    # ---- 6. Business logic top 10 ----
    bl_items = ar.get("business_logic_items", [])
    sections.append(
        pn.pane.HTML(
            '<h3 style="color:#eee;margin-top:1rem">Top Business Logic Items</h3>',
            sizing_mode="stretch_width",
        ),
    )
    sections.append(pn.pane.HTML(_business_logic_table(bl_items), sizing_mode="stretch_width"))

    return pn.Column(*sections, sizing_mode="stretch_width")
