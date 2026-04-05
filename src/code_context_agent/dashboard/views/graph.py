"""Graph explorer view: force-directed graph with filtering and detail panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import networkx as nx
    import panel as pn

    from .._data import DashboardData


def _empty_placeholder() -> pn.viewable.Viewable:
    """Return a placeholder when no graph data is available."""
    import panel as pn

    return pn.pane.Markdown(
        "# Graph Explorer\n\nNo graph data loaded. Run `code-context-agent index` first.",
        sizing_mode="stretch_width",
    )


def _compute_layout(G: nx.Graph, seed: int = 42) -> dict[str, tuple[float, float]]:
    """Pre-compute spring layout for the full graph (called once at build time).

    Args:
        G: NetworkX graph to lay out.
        seed: Random seed for deterministic layout.

    Returns:
        Dict mapping node id to (x, y) position.
    """
    import networkx as nx_mod

    if len(G) == 0:
        return {}
    # Use spring layout with tuned params for readability
    return nx_mod.spring_layout(G, k=0.5, iterations=50, seed=seed)


def _filter_subgraph(
    G: nx.MultiDiGraph,
    node_types: list[str],
    edge_types: list[str],
    search: str,
) -> nx.MultiDiGraph:
    """Build a filtered subgraph based on active node/edge types and search query.

    Args:
        G: Full NetworkX MultiDiGraph.
        node_types: Active node type strings.
        edge_types: Active edge type strings.
        search: Search text for node name filtering.

    Returns:
        Filtered subgraph as a new MultiDiGraph.
    """
    import networkx as nx_mod

    node_type_set = set(node_types)
    edge_type_set = set(edge_types)

    # Filter nodes by type
    keep_nodes = {n for n, d in G.nodes(data=True) if d.get("node_type", "unknown") in node_type_set}

    # If search is active, further restrict to matching nodes + 1-hop neighbors
    if search and search.strip():
        query = search.strip().lower()
        matches = set()
        for n in keep_nodes:
            node_data = G.nodes[n]
            node_name = node_data.get("name", str(n)).lower()
            node_id = str(n).lower()
            if query in node_name or query in node_id:
                matches.add(n)
        # Add 1-hop neighbors of matches (that pass type filter)
        neighbors: set[str] = set()
        for m in matches:
            for nbr in G.predecessors(m):
                if nbr in keep_nodes:
                    neighbors.add(nbr)
            for nbr in G.successors(m):
                if nbr in keep_nodes:
                    neighbors.add(nbr)
        keep_nodes = matches | neighbors

    # Build subgraph with filtered edges
    sub = nx_mod.MultiDiGraph()
    for n in keep_nodes:
        sub.add_node(n, **G.nodes[n])

    for u, v, k, d in G.edges(keys=True, data=True):
        if u in keep_nodes and v in keep_nodes and d.get("edge_type", k) in edge_type_set:
            sub.add_edge(u, v, key=k, **d)

    return sub


def _graph_stats_markdown(G: nx.MultiDiGraph) -> str:
    """Generate a markdown summary of graph statistics.

    Args:
        G: The (sub)graph to describe.

    Returns:
        Markdown string with node/edge/component counts.
    """
    import networkx as nx_mod

    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    try:
        n_components = nx_mod.number_weakly_connected_components(G)
    except Exception:
        n_components = 0

    # Node type distribution
    type_counts: dict[str, int] = {}
    for _, d in G.nodes(data=True):
        nt = d.get("node_type", "unknown")
        type_counts[nt] = type_counts.get(nt, 0) + 1

    # Edge type distribution
    edge_counts: dict[str, int] = {}
    for _, _, _, d in G.edges(keys=True, data=True):
        et = d.get("edge_type", "unknown")
        edge_counts[et] = edge_counts.get(et, 0) + 1

    lines = [
        "### Graph Statistics",
        "",
        f"**Nodes:** {n_nodes:,} | **Edges:** {n_edges:,} | **Components:** {n_components:,}",
        "",
    ]
    if type_counts:
        lines.append("**Node types:** " + ", ".join(f"{k}: {v}" for k, v in sorted(type_counts.items())))
    if edge_counts:
        lines.append("**Edge types:** " + ", ".join(f"{k}: {v}" for k, v in sorted(edge_counts.items())))

    return "\n".join(lines)


def _node_detail_markdown(G: nx.MultiDiGraph, node_id: str) -> str:
    """Generate a markdown detail card for a selected node.

    Args:
        G: The graph containing the node.
        node_id: The selected node ID.

    Returns:
        Markdown string with node details.
    """
    if not G.has_node(node_id):
        return f"Node `{node_id}` not found in current subgraph."

    d = G.nodes[node_id]
    lines = [
        "### Node Detail",
        "",
        f"**ID:** `{node_id}`",
        f"**Name:** {d.get('name', 'N/A')}",
        f"**Type:** {d.get('node_type', 'unknown')}",
        f"**File:** `{d.get('file_path', 'N/A')}`",
        f"**Lines:** {d.get('line_start', '?')} - {d.get('line_end', '?')}",
        "",
    ]

    # In-edges
    in_edges = list(G.in_edges(node_id, data=True))
    if in_edges:
        lines.append(f"**Incoming edges ({len(in_edges)}):**")
        for src, _, ed in in_edges[:20]:
            src_name = G.nodes[src].get("name", src) if G.has_node(src) else src
            lines.append(f"- {src_name} --[{ed.get('edge_type', '?')}]--> this")
        if len(in_edges) > 20:
            lines.append(f"- ... and {len(in_edges) - 20} more")

    # Out-edges
    out_edges = list(G.out_edges(node_id, data=True))
    if out_edges:
        lines.append(f"\n**Outgoing edges ({len(out_edges)}):**")
        for _, tgt, ed in out_edges[:20]:
            tgt_name = G.nodes[tgt].get("name", tgt) if G.has_node(tgt) else tgt
            lines.append(f"- this --[{ed.get('edge_type', '?')}]--> {tgt_name}")
        if len(out_edges) > 20:
            lines.append(f"- ... and {len(out_edges) - 20} more")

    return "\n".join(lines)


def _build_hv_graph(
    sub_G: nx.MultiDiGraph,
    full_pos: dict[str, tuple[float, float]],
    node_colors: dict[str, str],
    edge_colors: dict[str, str],
    fallback_color: str,
) -> object:
    """Build a HoloViews Graph element from the filtered subgraph.

    Args:
        sub_G: Filtered MultiDiGraph to render.
        full_pos: Pre-computed layout positions (full graph).
        node_colors: Mapping node_type -> hex color.
        edge_colors: Mapping edge_type -> hex color.
        fallback_color: Default color for unmapped types.

    Returns:
        HoloViews element (Graph or Overlay).
    """
    import holoviews as hv

    hv.extension("bokeh")

    n_nodes = sub_G.number_of_nodes()

    if n_nodes == 0:
        # Return an empty Points element with a message
        return hv.Text(0.5, 0.5, "No nodes match current filters").opts(text_color="#ccc")

    # Build position dict for subgraph, using pre-computed positions
    sub_pos = {}
    for n in sub_G.nodes:
        sub_pos[n] = full_pos.get(n, (0.0, 0.0))

    # Set display attributes on nodes for HoloViews
    for n in sub_G.nodes:
        nd = sub_G.nodes[n]
        nt = nd.get("node_type", "unknown")
        nd["color"] = node_colors.get(nt, fallback_color)
        nd["display_name"] = nd.get("name", str(n))
        nd["display_type"] = nt

    # Set edge display colors
    for _u, _v, k, d in sub_G.edges(keys=True, data=True):
        et = d.get("edge_type", k)
        d["color"] = edge_colors.get(et, fallback_color)

    # Create a simple DiGraph for HoloViews (it doesn't handle MultiDiGraph well)
    import networkx as nx_mod

    simple_G = nx_mod.DiGraph()
    for n, d in sub_G.nodes(data=True):
        simple_G.add_node(n, **d)
    for u, v, _k, d in sub_G.edges(keys=True, data=True):
        # If multiple edges exist, keep first encountered
        if not simple_G.has_edge(u, v):
            simple_G.add_edge(u, v, **d)

    hv_graph = hv.Graph.from_networkx(simple_G, sub_pos)

    use_datashader = n_nodes > 2000

    if use_datashader:
        from holoviews.operation.datashader import datashade

        # Datashade edges for performance, keep nodes interactive
        shaded_edges = datashade(hv_graph.edgepaths, cmap=["#4a4a6a"]).opts(
            width=950,
            height=620,
            bgcolor="#1a1a2e",
        )
        interactive_nodes = hv_graph.nodes.opts(
            size=5,
            color="color",
            tools=["hover", "tap"],
            hover_tooltips=[
                ("Name", "@display_name"),
                ("Type", "@display_type"),
                ("File", "@file_path"),
            ],
            line_color="#1a1a2e",
            line_width=0.5,
        )
        return shaded_edges * interactive_nodes
    else:
        # Full interactivity for smaller graphs
        node_size = max(4, min(12, 800 // max(n_nodes, 1)))
        return hv_graph.opts(
            node_size=node_size,
            node_color="color",
            node_line_color="#1a1a2e",
            node_line_width=0.5,
            edge_color="color",
            edge_line_width=1,
            edge_alpha=0.5,
            width=950,
            height=620,
            bgcolor="#1a1a2e",
            xaxis=None,
            yaxis=None,
            tools=["hover", "tap", "box_zoom", "wheel_zoom", "pan", "reset"],
            inspection_policy="nodes",
            hover_tooltips=[
                ("Name", "@display_name"),
                ("Type", "@display_type"),
                ("File", "@file_path"),
            ],
        )


def build_graph_view(data: DashboardData) -> pn.viewable.Viewable:
    """Build the graph explorer tab.

    Args:
        data: Dashboard data container with graph and raw data.

    Returns:
        Panel component with interactive graph explorer.
    """
    import panel as pn

    from .._theme import EDGE_COLORS, EDGE_TYPE_ORDER, FALLBACK_COLOR, NODE_COLORS, NODE_TYPE_ORDER

    if data.graph is None:
        return _empty_placeholder()

    G: nx.MultiDiGraph = data.graph._graph

    if G.number_of_nodes() == 0:
        return _empty_placeholder()

    # Discover actual node/edge types present in the graph
    present_node_types: list[str] = []
    seen_nt: set[str] = set()
    for _, d in G.nodes(data=True):
        nt = d.get("node_type", "unknown")
        if nt not in seen_nt:
            seen_nt.add(nt)
    # Preserve theme ordering for types that exist
    for nt in NODE_TYPE_ORDER:
        if nt in seen_nt:
            present_node_types.append(nt)
    for nt in sorted(seen_nt - set(NODE_TYPE_ORDER)):
        present_node_types.append(nt)

    present_edge_types: list[str] = []
    seen_et: set[str] = set()
    for _, _, _, d in G.edges(keys=True, data=True):
        et = d.get("edge_type", "unknown")
        if et not in seen_et:
            seen_et.add(et)
    for et in EDGE_TYPE_ORDER:
        if et in seen_et:
            present_edge_types.append(et)
    for et in sorted(seen_et - set(EDGE_TYPE_ORDER)):
        present_edge_types.append(et)

    # Pre-compute layout ONCE for the full graph
    full_pos = _compute_layout(G)

    # --- Widgets ---
    node_type_filter = pn.widgets.CheckBoxGroup(
        name="Node Types",
        options=present_node_types,
        value=present_node_types,
        inline=False,
    )
    edge_type_filter = pn.widgets.CheckBoxGroup(
        name="Edge Types",
        options=present_edge_types,
        value=present_edge_types,
        inline=False,
    )
    search_input = pn.widgets.TextInput(
        name="Search",
        placeholder="Search nodes...",
        width=200,
    )

    # --- Reactive graph builder ---
    def _render_graph(node_types: list[str], edge_types: list[str], search: str) -> object:
        """Build and return HoloViews graph for current filter state."""
        sub_G = _filter_subgraph(G, node_types, edge_types, search)
        return _build_hv_graph(sub_G, full_pos, NODE_COLORS, EDGE_COLORS, FALLBACK_COLOR)

    graph_pane = pn.bind(_render_graph, node_type_filter, edge_type_filter, search_input)

    # --- Node selection / tap callback ---
    selected_node_input = pn.widgets.TextInput(
        name="Selected Node ID",
        placeholder="Tap a node or type an ID...",
        width=300,
    )

    def _show_node_detail(node_id: str) -> str:
        """Show detail for a selected node."""
        if not node_id or not node_id.strip():
            return _graph_stats_markdown(G)
        return _node_detail_markdown(G, node_id.strip())

    detail_bound = pn.bind(_show_node_detail, selected_node_input)
    detail_pane = pn.pane.Markdown(
        detail_bound,
        sizing_mode="stretch_width",
        styles={"background": "#16162a", "padding": "12px", "border-radius": "8px"},
    )

    # --- Layout ---
    filter_sidebar = pn.Column(
        pn.pane.Markdown("### Filters", styles={"color": "#eee"}),
        search_input,
        pn.pane.Markdown("**Node Types**", styles={"color": "#ccc"}),
        node_type_filter,
        pn.pane.Markdown("**Edge Types**", styles={"color": "#ccc"}),
        edge_type_filter,
        width=200,
        styles={"background": "#16162a", "padding": "8px", "border-radius": "8px"},
    )

    detail_section = pn.Column(
        pn.pane.Markdown("### Details", styles={"color": "#eee"}),
        selected_node_input,
        detail_pane,
        width=320,
        styles={"background": "#16162a", "padding": "8px", "border-radius": "8px"},
    )

    graph_area = pn.Column(
        pn.pane.HoloViews(graph_pane, sizing_mode="stretch_width"),
        sizing_mode="stretch_width",
    )

    main_row = pn.Row(
        filter_sidebar,
        graph_area,
        detail_section,
        sizing_mode="stretch_width",
    )

    return pn.Column(
        pn.pane.Markdown("# Graph Explorer", styles={"color": "#eee"}),
        main_row,
        sizing_mode="stretch_width",
    )
