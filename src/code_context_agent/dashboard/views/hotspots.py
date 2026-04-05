"""Hotspots view: degree centrality analysis, entry points, distribution charts."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import panel as pn

    from .._data import DashboardData


def _compute_degree_data(data: DashboardData) -> list[dict]:
    """Compute in-degree, out-degree, and total degree for every node.

    Falls back to raw graph data if the CodeGraph instance is unavailable.

    Args:
        data: Dashboard data container.

    Returns:
        List of dicts with id, name, node_type, file_path, in_degree, out_degree, total_degree.
    """
    if data.graph is not None:
        G = data.graph._graph
        in_deg = dict(G.in_degree())
        out_deg = dict(G.out_degree())
        nodes_data: list[dict] = []
        for node_id in G.nodes:
            attrs = G.nodes[node_id]
            nodes_data.append(
                {
                    "id": node_id,
                    "name": attrs.get("name", node_id),
                    "node_type": attrs.get("node_type", "unknown"),
                    "file_path": attrs.get("file_path", ""),
                    "in_degree": in_deg.get(node_id, 0),
                    "out_degree": out_deg.get(node_id, 0),
                    "total_degree": in_deg.get(node_id, 0) + out_deg.get(node_id, 0),
                },
            )
        return nodes_data

    # Fallback: reconstruct from raw graph data
    raw_nodes = data.graph_raw.get("nodes", [])
    raw_links = data.graph_raw.get("links", data.graph_raw.get("edges", []))
    in_counts: dict[str, int] = {}
    out_counts: dict[str, int] = {}
    for link in raw_links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        out_counts[src] = out_counts.get(src, 0) + 1
        in_counts[tgt] = in_counts.get(tgt, 0) + 1

    nodes_data = []
    for node in raw_nodes:
        nid = node.get("id", "")
        ind = in_counts.get(nid, 0)
        outd = out_counts.get(nid, 0)
        nodes_data.append(
            {
                "id": nid,
                "name": node.get("name", nid),
                "node_type": node.get("node_type", "unknown"),
                "file_path": node.get("file_path", ""),
                "in_degree": ind,
                "out_degree": outd,
                "total_degree": ind + outd,
            },
        )
    return nodes_data


def _build_top_hotspots_chart(records: list[dict]) -> object:
    """Build horizontal bar chart of top 20 nodes by total degree.

    Args:
        records: Full list of node degree dicts.

    Returns:
        Altair Chart object.
    """
    import altair as alt

    from .._theme import FALLBACK_COLOR, NODE_COLORS, NODE_TYPE_ORDER

    sorted_recs = sorted(records, key=lambda r: r["total_degree"], reverse=True)[:20]

    color_domain = NODE_TYPE_ORDER + [t for t in {r["node_type"] for r in sorted_recs} if t not in NODE_TYPE_ORDER]
    color_range = [NODE_COLORS.get(t, FALLBACK_COLOR) for t in color_domain]

    chart = (
        alt.Chart(alt.Data(values=sorted_recs))
        .mark_bar()
        .encode(
            x=alt.X("total_degree:Q", title="Total Degree"),
            y=alt.Y("name:N", sort="-x", title=None),
            color=alt.Color(
                "node_type:N",
                scale=alt.Scale(domain=color_domain, range=color_range),
                legend=alt.Legend(title="Node Type"),
            ),
            tooltip=[
                alt.Tooltip("name:N", title="Name"),
                alt.Tooltip("file_path:N", title="File"),
                alt.Tooltip("node_type:N", title="Type"),
                alt.Tooltip("in_degree:Q", title="In-degree"),
                alt.Tooltip("out_degree:Q", title="Out-degree"),
                alt.Tooltip("total_degree:Q", title="Total degree"),
            ],
        )
        .properties(width="container", height=500, title="Top 20 Hotspots by Total Degree")
    )
    return chart


def _build_entry_points_table(records: list[dict], *, pre_filtered: bool = False) -> str:
    """Build HTML table of entry point nodes (high out-degree, low in-degree).

    Args:
        records: Node degree dicts — either the full list or pre-filtered entries.
        pre_filtered: If True, *records* are already filtered and sorted (e.g. from a DuckDB query).

    Returns:
        HTML string for the table.
    """
    if pre_filtered:
        entries = records
    else:
        entries = sorted(
            [r for r in records if r["in_degree"] <= 1],
            key=lambda r: r["out_degree"],
            reverse=True,
        )[:20]

    if not entries:
        return "<p style='color:#aaa;'>No entry points detected (nodes with in-degree &le; 1).</p>"

    import html as html_mod

    rows_html = ""
    for row in entries:
        name = html_mod.escape(str(row["name"]))
        fpath = html_mod.escape(str(row["file_path"]))
        ntype = html_mod.escape(str(row["node_type"]))
        rows_html += (
            f"<tr>"
            f"<td style='padding:6px 12px; border-bottom:1px solid #2a2a3e;'>{name}</td>"
            f"<td style='padding:6px 12px; border-bottom:1px solid #2a2a3e; font-size:0.85em; color:#888;'>"
            f"{fpath}</td>"
            f"<td style='padding:6px 12px; border-bottom:1px solid #2a2a3e; text-align:right;'>"
            f"{row['out_degree']}</td>"
            f"<td style='padding:6px 12px; border-bottom:1px solid #2a2a3e;'>{ntype}</td>"
            f"</tr>"
        )

    return f"""
    <table style="width:100%; border-collapse:collapse; color:#ccc; font-family:system-ui, sans-serif;">
      <thead>
        <tr style="border-bottom:2px solid #444;">
          <th style="padding:8px 12px; text-align:left;">Name</th>
          <th style="padding:8px 12px; text-align:left;">File</th>
          <th style="padding:8px 12px; text-align:right;">Out-degree</th>
          <th style="padding:8px 12px; text-align:left;">Type</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    """


def _build_scatter_chart(records: list[dict]) -> object:
    """Build in/out degree scatter plot with interactive zoom.

    Args:
        records: Full list of node degree dicts.

    Returns:
        Altair Chart object.
    """
    import altair as alt

    from .._theme import FALLBACK_COLOR, NODE_COLORS, NODE_TYPE_ORDER

    color_domain = NODE_TYPE_ORDER + [t for t in {r["node_type"] for r in records} if t not in NODE_TYPE_ORDER]
    color_range = [NODE_COLORS.get(t, FALLBACK_COLOR) for t in color_domain]

    chart = (
        alt.Chart(alt.Data(values=records))
        .mark_circle(opacity=0.7)
        .encode(
            x=alt.X("out_degree:Q", title="Out-degree"),
            y=alt.Y("in_degree:Q", title="In-degree"),
            color=alt.Color(
                "node_type:N",
                scale=alt.Scale(domain=color_domain, range=color_range),
                legend=alt.Legend(title="Node Type"),
            ),
            size=alt.Size("total_degree:Q", legend=alt.Legend(title="Total Degree"), scale=alt.Scale(range=[20, 400])),
            tooltip=[
                alt.Tooltip("name:N", title="Name"),
                alt.Tooltip("file_path:N", title="File"),
                alt.Tooltip("node_type:N", title="Type"),
                alt.Tooltip("in_degree:Q", title="In-degree"),
                alt.Tooltip("out_degree:Q", title="Out-degree"),
            ],
        )
        .properties(width="container", height=400, title="In-degree vs Out-degree")
        .interactive()
    )
    return chart


def _build_degree_histogram(records: list[dict]) -> object:
    """Build histogram of total degree distribution.

    Args:
        records: Full list of node degree dicts.

    Returns:
        Altair Chart object.
    """
    import altair as alt

    degree_records = [{"degree": r["total_degree"]} for r in records]

    chart = (
        alt.Chart(alt.Data(values=degree_records))
        .mark_bar(color="#7C3AED")
        .encode(
            x=alt.X("degree:Q", bin=alt.Bin(maxbins=30), title="Total Degree"),
            y=alt.Y("count()", title="Number of Nodes"),
        )
        .properties(width="container", height=300, title="Degree Distribution")
    )
    return chart


def _get_entry_points_from_cache(data: DashboardData) -> list[dict] | None:
    """Try to fetch entry points via DuckDB query on the cached degree table.

    Args:
        data: Dashboard data container.

    Returns:
        List of dicts with name, file_path, out_degree, node_type, or None if cache unavailable.
    """
    if data.cache.duckdb_con is None:
        return None
    try:
        return data.cache.query(
            "SELECT name, file_path, out_degree, node_type "
            "FROM degree WHERE in_degree <= 1 AND out_degree > 0 "
            "ORDER BY out_degree DESC LIMIT 20",
        ).to_dicts()
    except Exception:
        return None


def build_hotspots_view(data: DashboardData) -> pn.viewable.Viewable:
    """Build the hotspots tab with degree centrality analysis, entry points, and distribution charts.

    Args:
        data: Dashboard data container with graph information.

    Returns:
        Panel Column layout with all hotspot visualizations.
    """
    import panel as pn

    # Use cached degree data if available, otherwise compute from graph
    records = data.cache.degree_df.to_dicts() if data.cache.degree_df is not None else _compute_degree_data(data)

    # Handle missing graph data
    if not records:
        return pn.pane.Markdown(
            "# Hotspots\n\nNo graph data available. Run `code-context-agent index` first.",
            sizing_mode="stretch_width",
        )

    # Summary stats
    total_nodes = len(records)
    total_edges = 0
    if data.cache.edge_type_counts is not None:
        total_edges = int(data.cache.edge_type_counts["count"].sum())
    elif data.graph is not None:
        total_edges = data.graph.edge_count
    else:
        total_edges = len(data.graph_raw.get("links", data.graph_raw.get("edges", [])))

    degrees = [r["total_degree"] for r in records]
    max_degree = max(degrees) if degrees else 0
    avg_degree = sum(degrees) / len(degrees) if degrees else 0.0

    header = pn.pane.Markdown(
        f"# Hotspots\n\n"
        f"**{total_nodes}** nodes | **{total_edges}** edges | "
        f"max degree **{max_degree}** | avg degree **{avg_degree:.1f}**",
        sizing_mode="stretch_width",
    )

    # Top 20 hotspots bar chart
    hotspots_chart = pn.pane.Vega(_build_top_hotspots_chart(records), sizing_mode="stretch_width")

    # Entry points table — prefer DuckDB query, fall back to in-memory filtering
    entry_header = pn.pane.Markdown(
        "## Entry Points\n\nNodes with high out-degree and low in-degree (in-degree &le; 1) "
        "are likely entry points, CLI handlers, or top-level orchestrators.",
        sizing_mode="stretch_width",
    )
    cached_entries = _get_entry_points_from_cache(data)
    if cached_entries is not None:
        entry_table = pn.pane.HTML(
            _build_entry_points_table(cached_entries, pre_filtered=True),
            sizing_mode="stretch_width",
        )
    else:
        entry_table = pn.pane.HTML(_build_entry_points_table(records), sizing_mode="stretch_width")

    # Scatter plot
    scatter_chart = pn.pane.Vega(_build_scatter_chart(records), sizing_mode="stretch_width")

    # Degree distribution histogram
    histogram_chart = pn.pane.Vega(_build_degree_histogram(records), sizing_mode="stretch_width")

    return pn.Column(
        header,
        pn.layout.Divider(),
        hotspots_chart,
        pn.layout.Divider(),
        entry_header,
        entry_table,
        pn.layout.Divider(),
        scatter_chart,
        pn.layout.Divider(),
        pn.pane.Markdown("## Degree Distribution", sizing_mode="stretch_width"),
        histogram_chart,
        sizing_mode="stretch_width",
    )
