"""Modules view: community detection and module visualization."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import networkx as nx
    import panel as pn

    from .._data import DashboardData


# Palette for community coloring (20 distinct colors, cycling for larger community counts)
_COMMUNITY_PALETTE = [
    "#a78bfa",
    "#34d399",
    "#60a5fa",
    "#fbbf24",
    "#f472b6",
    "#fb923c",
    "#22d3ee",
    "#ef4444",
    "#84cc16",
    "#e879f9",
    "#2dd4bf",
    "#f97316",
    "#818cf8",
    "#facc15",
    "#06b6d4",
    "#ec4899",
    "#10b981",
    "#6366f1",
    "#f59e0b",
    "#14b8a6",
]


def _empty_placeholder() -> pn.viewable.Viewable:
    """Return a placeholder when no graph data is available."""
    import panel as pn

    return pn.pane.Markdown(
        "# Modules\n\nNo graph data loaded. Run `code-context-agent index` first.",
        sizing_mode="stretch_width",
    )


def _detect_communities(G: nx.MultiDiGraph) -> list[set[str]]:
    """Run Louvain community detection on the graph.

    Args:
        G: NetworkX MultiDiGraph to partition.

    Returns:
        List of sets of node IDs, sorted by community size (largest first).
    """
    from networkx.algorithms.community import louvain_communities

    # Louvain requires undirected graph
    undirected = G.to_undirected()
    try:
        communities = louvain_communities(undirected, seed=42)
    except Exception:
        # Fallback: each weakly connected component is a community
        import networkx as nx_mod

        communities = list(nx_mod.weakly_connected_components(G))

    # Sort by size, largest first
    result: list[set[str]] = sorted(communities, key=len, reverse=True)  # type: ignore[arg-type]
    return result


def _community_summary_markdown(communities: list[set[str]], G: nx.MultiDiGraph) -> str:
    """Generate a markdown summary of all detected communities.

    Args:
        communities: List of node-ID sets.
        G: The graph for node metadata lookup.

    Returns:
        Markdown string describing communities.
    """
    lines = [
        f"### {len(communities)} Communities Detected",
        "",
        f"**Total nodes:** {G.number_of_nodes():,}",
        "",
        "| # | Size | Top Types | Representative Nodes |",
        "|---|------|-----------|---------------------|",
    ]

    for i, community in enumerate(communities[:30]):
        # Count node types in community
        type_counts: dict[str, int] = {}
        sample_names: list[str] = []
        for n in community:
            nd = G.nodes[n]
            nt = nd.get("node_type", "unknown")
            type_counts[nt] = type_counts.get(nt, 0) + 1
            if len(sample_names) < 3:
                sample_names.append(nd.get("name", str(n)))

        top_types = ", ".join(f"{k}({v})" for k, v in sorted(type_counts.items(), key=lambda x: -x[1])[:3])
        samples = ", ".join(sample_names)
        color = _COMMUNITY_PALETTE[i % len(_COMMUNITY_PALETTE)]
        lines.append(f"| <span style='color:{color}'>C{i}</span> | {len(community)} | {top_types} | {samples} |")

    if len(communities) > 30:
        lines.append(f"| ... | | | +{len(communities) - 30} more communities |")

    return "\n".join(lines)


def _community_detail_markdown(
    community_idx: int,
    communities: list[set[str]],
    G: nx.MultiDiGraph,
) -> str:
    """Generate a detailed markdown view of a single community.

    Args:
        community_idx: Index of the community to detail.
        communities: List of all communities.
        G: The graph for node metadata lookup.

    Returns:
        Markdown string with community member details.
    """
    if community_idx < 0 or community_idx >= len(communities):
        return "Select a community from the list to see details."

    community = communities[community_idx]
    color = _COMMUNITY_PALETTE[community_idx % len(_COMMUNITY_PALETTE)]

    lines = [
        f"### <span style='color:{color}'>Community {community_idx}</span> ({len(community)} nodes)",
        "",
    ]

    # Group by node type
    by_type: dict[str, list[tuple[str, dict]]] = {}
    for n in community:
        nd = G.nodes[n]
        nt = nd.get("node_type", "unknown")
        by_type.setdefault(nt, []).append((n, dict(nd)))

    for nt in sorted(by_type.keys()):
        members = by_type[nt]
        lines.append(f"**{nt}** ({len(members)})")
        lines.append("")
        lines.append("| Name | File | Lines |")
        lines.append("|------|------|-------|")
        # Sort by name, show up to 50
        for node_id, nd in sorted(members, key=lambda x: x[1].get("name", x[0]))[:50]:
            name = nd.get("name", node_id)
            fpath = nd.get("file_path", "")
            # Shorten file path for display
            if len(fpath) > 60:
                fpath = "..." + fpath[-57:]
            ls = nd.get("line_start", "?")
            le = nd.get("line_end", "?")
            lines.append(f"| {name} | `{fpath}` | {ls}-{le} |")
        if len(members) > 50:
            lines.append(f"| ... | | +{len(members) - 50} more |")
        lines.append("")

    # Internal edges summary
    internal_edges = 0
    external_edges = 0
    for u, v, _, _ in G.edges(keys=True, data=True):
        if u in community and v in community:
            internal_edges += 1
        elif u in community or v in community:
            external_edges += 1

    lines.append(f"**Internal edges:** {internal_edges} | **External edges:** {external_edges}")
    if internal_edges + external_edges > 0:
        cohesion = internal_edges / (internal_edges + external_edges)
        lines.append(f"**Cohesion:** {cohesion:.1%}")

    return "\n".join(lines)


def _build_community_graph(
    G: nx.MultiDiGraph,
    communities: list[set[str]],
    full_pos: dict[str, tuple[float, float]],
    selected_community: int,
) -> object:
    """Build a HoloViews Graph colored by community assignment.

    Args:
        G: Full MultiDiGraph.
        communities: Community partition.
        full_pos: Pre-computed layout positions.
        selected_community: Index of community to highlight (-1 for all).

    Returns:
        HoloViews element for rendering.
    """
    import holoviews as hv
    import networkx as nx_mod

    hv.extension("bokeh")

    # Build community membership lookup
    node_to_community: dict[str, int] = {}
    for i, community in enumerate(communities):
        for n in community:
            node_to_community[n] = i

    # Decide which nodes to show
    if selected_community >= 0 and selected_community < len(communities):
        # Show selected community + its immediate neighbors
        focus_nodes = set(communities[selected_community])
        neighbor_nodes: set[str] = set()
        for n in focus_nodes:
            for nbr in G.predecessors(n):
                neighbor_nodes.add(nbr)
            for nbr in G.successors(n):
                neighbor_nodes.add(nbr)
        show_nodes = focus_nodes | neighbor_nodes
    else:
        show_nodes = set(G.nodes)

    if not show_nodes:
        return hv.Text(0.5, 0.5, "No nodes to display").opts(text_color="#ccc")

    # Build simple DiGraph for HoloViews
    simple_G = nx_mod.DiGraph()
    for n in show_nodes:
        if G.has_node(n):
            nd = dict(G.nodes[n])
            c_idx = node_to_community.get(n, 0)
            nd["color"] = _COMMUNITY_PALETTE[c_idx % len(_COMMUNITY_PALETTE)]
            nd["community"] = f"C{c_idx}"
            nd["display_name"] = nd.get("name", str(n))
            nd["display_type"] = nd.get("node_type", "unknown")
            # Dim neighbors when a community is selected
            if selected_community >= 0 and n not in communities[selected_community]:
                nd["alpha"] = 0.3
                nd["color"] = "#3a3a4e"
            else:
                nd["alpha"] = 1.0
            simple_G.add_node(n, **nd)

    for u, v, _, d in G.edges(keys=True, data=True):
        if u in show_nodes and v in show_nodes and not simple_G.has_edge(u, v):
            simple_G.add_edge(u, v, **d)

    sub_pos = {n: full_pos[n] for n in simple_G.nodes if n in full_pos}
    # Fallback for nodes without positions
    for n in simple_G.nodes:
        if n not in sub_pos:
            sub_pos[n] = (0.0, 0.0)

    n_nodes = simple_G.number_of_nodes()

    if n_nodes > 2000:
        from holoviews.operation.datashader import datashade

        hv_graph = hv.Graph.from_networkx(simple_G, sub_pos)
        shaded = datashade(hv_graph.edgepaths, cmap=["#4a4a6a"]).opts(
            width=800,
            height=550,
            bgcolor="#1a1a2e",
        )
        nodes = hv_graph.nodes.opts(
            size=5,
            color="color",
            tools=["hover", "tap"],
            hover_tooltips=[
                ("Name", "@display_name"),
                ("Type", "@display_type"),
                ("Community", "@community"),
            ],
            line_color="#1a1a2e",
        )
        return shaded * nodes
    else:
        hv_graph = hv.Graph.from_networkx(simple_G, sub_pos)
        node_size = max(4, min(12, 800 // max(n_nodes, 1)))
        return hv_graph.opts(
            node_size=node_size,
            node_color="color",
            node_line_color="#1a1a2e",
            node_line_width=0.5,
            edge_color="#4a4a6a",
            edge_line_width=1,
            edge_alpha=0.3,
            width=800,
            height=550,
            bgcolor="#1a1a2e",
            xaxis=None,
            yaxis=None,
            tools=["hover", "tap", "box_zoom", "wheel_zoom", "pan", "reset"],
            inspection_policy="nodes",
            hover_tooltips=[
                ("Name", "@display_name"),
                ("Type", "@display_type"),
                ("Community", "@community"),
            ],
        )


def _communities_from_cache(data: DashboardData) -> list[set[str]] | None:
    """Convert cached community assignments to the list-of-sets format.

    Args:
        data: Dashboard data container with pre-computed cache.

    Returns:
        Sorted list of node-ID sets (largest first), or None if cache unavailable.
    """
    if data.cache.community_assignments is None:
        return None

    comm_df = data.cache.community_assignments
    if len(comm_df) == 0:
        return None

    communities_dict: dict[int, set[str]] = {}
    for row in comm_df.iter_rows(named=True):
        cid = row["community_id"]
        if cid not in communities_dict:
            communities_dict[cid] = set()
        communities_dict[cid].add(row["id"])

    # Sort by size descending (matches _detect_communities output order)
    return sorted(communities_dict.values(), key=len, reverse=True)


def build_modules_view(data: DashboardData) -> pn.viewable.Viewable:
    """Build the modules tab with community detection and visualization.

    Args:
        data: Dashboard data container with graph and raw data.

    Returns:
        Panel component with community detection results and graph.
    """
    import panel as pn

    if data.graph is None:
        return _empty_placeholder()

    G: nx.MultiDiGraph = data.graph._graph

    if G.number_of_nodes() == 0:
        return _empty_placeholder()

    # Use cached Louvain assignments if available; fall back to on-the-fly detection
    communities = _communities_from_cache(data)
    if communities is None:
        communities = _detect_communities(G)

    if not communities:
        return pn.Column(
            pn.pane.Markdown("# Modules\n\nNo communities detected in the graph."),
            sizing_mode="stretch_width",
        )

    # Pre-compute layout once
    full_pos = _compute_layout(G)

    # --- Summary ---
    summary_md = pn.pane.Markdown(
        _community_summary_markdown(communities, G),
        sizing_mode="stretch_width",
        styles={"background": "#16162a", "padding": "12px", "border-radius": "8px"},
    )

    # --- Community selector ---
    community_options = {"All communities": -1}
    for i, c in enumerate(communities[:30]):
        top_name = ""
        for n in c:
            nd = G.nodes[n]
            name = nd.get("name", str(n))
            if nd.get("node_type") in ("class", "module", "file"):
                top_name = name
                break
        if not top_name and c:
            top_name = G.nodes[next(iter(c))].get("name", "")
        label = f"C{i}: {top_name} ({len(c)} nodes)"
        community_options[label] = i

    community_selector = pn.widgets.Select(
        name="Community",
        options=community_options,
        value=-1,
        width=350,
    )

    # --- Reactive graph ---
    def _render_community_graph(selected: int) -> object:
        """Build graph visualization for selected community."""
        return _build_community_graph(G, communities, full_pos, selected)

    graph_pane = pn.pane.HoloViews(
        pn.bind(_render_community_graph, community_selector),
        sizing_mode="stretch_width",
    )

    # --- Reactive detail ---
    def _render_detail(selected: int) -> str:
        """Build detail markdown for selected community."""
        return _community_detail_markdown(selected, communities, G)

    detail_pane = pn.pane.Markdown(
        pn.bind(_render_detail, community_selector),
        sizing_mode="stretch_width",
        styles={"background": "#16162a", "padding": "12px", "border-radius": "8px"},
    )

    # --- Layout ---
    controls = pn.Row(
        community_selector,
        pn.pane.Markdown(
            f"*Louvain community detection found **{len(communities)}** modules*",
            styles={"color": "#aaa", "padding-top": "8px"},
        ),
    )

    main_content = pn.Row(
        pn.Column(
            graph_pane,
            sizing_mode="stretch_width",
        ),
        pn.Column(
            detail_pane,
            width=400,
        ),
    )

    return pn.Column(
        pn.pane.Markdown("# Modules", styles={"color": "#eee"}),
        controls,
        summary_md,
        main_content,
        sizing_mode="stretch_width",
    )


def _compute_layout(G: nx.Graph, seed: int = 42) -> dict[str, tuple[float, float]]:
    """Pre-compute spring layout for the full graph.

    Args:
        G: NetworkX graph to lay out.
        seed: Random seed for deterministic layout.

    Returns:
        Dict mapping node id to (x, y) position.
    """
    import networkx as nx_mod

    if len(G) == 0:
        return {}
    return nx_mod.spring_layout(G, k=0.5, iterations=50, seed=seed)
