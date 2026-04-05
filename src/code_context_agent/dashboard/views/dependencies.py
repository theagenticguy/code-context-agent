"""Dependencies view: bidirectional dependency tree from selected symbol."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import panel as pn

    from .._data import DashboardData

# Edge types relevant for dependency analysis (excluding structural/heuristic edges).
_DEFAULT_EDGE_TYPES = frozenset({"imports", "calls", "inherits", "implements", "references"})
_ALL_FILTERABLE_EDGE_TYPES = [
    "imports",
    "calls",
    "inherits",
    "implements",
    "references",
    "contains",
    "cochanges",
    "similar_to",
    "tests",
]


def _bfs_tree(
    G: object,
    root: str,
    direction: str = "out",
    max_depth: int = 4,
    edge_types: frozenset[str] | None = None,
) -> list[set[str]]:
    """BFS traversal to collect dependency levels from a root node.

    Args:
        G: NetworkX MultiDiGraph instance.
        root: Node ID to start from.
        direction: "out" for outgoing dependencies, "in" for incoming dependents.
        max_depth: Maximum BFS depth.
        edge_types: Set of edge type strings to traverse. None means all.

    Returns:
        List of sets, one per BFS level (level 0 = {root}).
    """
    visited = {root}
    levels: list[set[str]] = [{root}]
    for _ in range(max_depth):
        next_level: set[str] = set()
        for node in levels[-1]:
            if direction == "out":
                neighbors = [
                    t
                    for _, t, k, _d in G.out_edges(node, keys=True, data=True)
                    if (edge_types is None or k in edge_types) and t not in visited
                ]
            else:
                neighbors = [
                    s
                    for s, _, k, _d in G.in_edges(node, keys=True, data=True)
                    if (edge_types is None or k in edge_types) and s not in visited
                ]
            next_level.update(neighbors)
            visited.update(neighbors)
        if not next_level:
            break
        levels.append(next_level)
    return levels


def _collect_tree_records(
    G: object,
    root: str,
    direction: str,
    max_depth: int,
    edge_types: frozenset[str] | None,
) -> list[dict]:
    """Collect records for tree visualization with pre-computed x/y positions.

    Args:
        G: NetworkX MultiDiGraph.
        root: Starting node ID.
        direction: "out" or "in".
        max_depth: BFS depth limit.
        edge_types: Edge types to traverse.

    Returns:
        List of dicts with fields: id, name, node_type, level, y_pos, direction.
    """
    levels = _bfs_tree(G, root, direction=direction, max_depth=max_depth, edge_types=edge_types)
    records: list[dict] = []
    for level_idx, level_nodes in enumerate(levels):
        sorted_nodes = sorted(level_nodes)
        for y_idx, node_id in enumerate(sorted_nodes):
            attrs = G.nodes.get(node_id, {})
            records.append(
                {
                    "id": node_id,
                    "name": attrs.get("name", node_id),
                    "node_type": attrs.get("node_type", "unknown"),
                    "file_path": attrs.get("file_path", ""),
                    "level": level_idx if direction == "out" else -level_idx,
                    "y_pos": y_idx,
                    "direction": direction,
                },
            )
    return records


def _collect_tree_edges(
    G: object,
    root: str,
    direction: str,
    max_depth: int,
    edge_types: frozenset[str] | None,
) -> list[dict]:
    """Collect edge records for drawing lines in the tree.

    Args:
        G: NetworkX MultiDiGraph.
        root: Starting node ID.
        direction: "out" or "in".
        max_depth: BFS depth limit.
        edge_types: Edge types to traverse.

    Returns:
        List of dicts with source_level, source_y, target_level, target_y, edge_type.
    """
    levels = _bfs_tree(G, root, direction=direction, max_depth=max_depth, edge_types=edge_types)
    # Build position lookup
    pos: dict[str, tuple[int, int]] = {}
    for level_idx, level_nodes in enumerate(levels):
        sorted_nodes = sorted(level_nodes)
        for y_idx, node_id in enumerate(sorted_nodes):
            lv = level_idx if direction == "out" else -level_idx
            pos[node_id] = (lv, y_idx)

    edge_records: list[dict] = []
    all_nodes = set()
    for level_nodes in levels:
        all_nodes.update(level_nodes)

    for node_id in all_nodes:
        if direction == "out":
            for _, tgt, k, _d in G.out_edges(node_id, keys=True, data=True):
                if tgt in all_nodes and (edge_types is None or k in edge_types) and tgt != node_id:
                    if node_id in pos and tgt in pos:
                        edge_records.append(
                            {
                                "source_level": pos[node_id][0],
                                "source_y": pos[node_id][1],
                                "target_level": pos[tgt][0],
                                "target_y": pos[tgt][1],
                                "edge_type": k,
                            },
                        )
        else:
            for src, _, k, _d in G.in_edges(node_id, keys=True, data=True):
                if src in all_nodes and (edge_types is None or k in edge_types) and src != node_id:
                    if node_id in pos and src in pos:
                        edge_records.append(
                            {
                                "source_level": pos[node_id][0],
                                "source_y": pos[node_id][1],
                                "target_level": pos[src][0],
                                "target_y": pos[src][1],
                                "edge_type": k,
                            },
                        )

    return edge_records


def _build_tree_chart(
    G: object,
    root: str,
    edge_types: frozenset[str] | None,
    max_depth: int = 4,
) -> object:
    """Build a bidirectional dependency tree visualization using Altair.

    The root node is at x=0. Outgoing dependencies extend to the right (positive x),
    incoming dependents extend to the left (negative x).

    Args:
        G: NetworkX MultiDiGraph.
        root: Node ID for the tree root.
        edge_types: Edge types to include.
        max_depth: BFS depth limit.

    Returns:
        Altair LayerChart combining nodes and edges.
    """
    import altair as alt

    from .._theme import EDGE_COLORS, FALLBACK_COLOR, NODE_COLORS, NODE_TYPE_ORDER

    # Collect outgoing and incoming trees
    out_records = _collect_tree_records(G, root, "out", max_depth, edge_types)
    in_records = _collect_tree_records(G, root, "in", max_depth, edge_types)

    # Merge, dedup root (appears in both)
    seen_ids: set[str] = set()
    all_records: list[dict] = []
    for rec in out_records + in_records:
        if rec["id"] not in seen_ids:
            all_records.append(rec)
            seen_ids.add(rec["id"])

    if not all_records:
        return alt.Chart(alt.Data(values=[{"x": 0, "y": 0}])).mark_text(text="No dependencies found", color="#888")

    # Collect edges
    out_edges = _collect_tree_edges(G, root, "out", max_depth, edge_types)
    in_edges = _collect_tree_edges(G, root, "in", max_depth, edge_types)
    all_edges = out_edges + in_edges

    # Color scales
    node_types_present = sorted({r["node_type"] for r in all_records})
    node_color_domain = [t for t in NODE_TYPE_ORDER if t in node_types_present] + [
        t for t in node_types_present if t not in NODE_TYPE_ORDER
    ]
    node_color_range = [NODE_COLORS.get(t, FALLBACK_COLOR) for t in node_color_domain]

    # Nodes layer
    nodes_chart = (
        alt.Chart(alt.Data(values=all_records))
        .mark_circle(size=120, opacity=0.9)
        .encode(
            x=alt.X("level:Q", title="Dependency Depth", axis=alt.Axis(tickMinStep=1)),
            y=alt.Y("y_pos:Q", title=None, axis=None),
            color=alt.Color(
                "node_type:N",
                scale=alt.Scale(domain=node_color_domain, range=node_color_range),
                legend=alt.Legend(title="Node Type"),
            ),
            tooltip=[
                alt.Tooltip("name:N", title="Name"),
                alt.Tooltip("file_path:N", title="File"),
                alt.Tooltip("node_type:N", title="Type"),
                alt.Tooltip("direction:N", title="Direction"),
            ],
        )
    )

    # Node labels layer
    labels_chart = (
        alt.Chart(alt.Data(values=all_records))
        .mark_text(dx=12, align="left", fontSize=11, color="#ccc")
        .encode(
            x=alt.X("level:Q"),
            y=alt.Y("y_pos:Q"),
            text=alt.Text("name:N"),
        )
    )

    layers = [nodes_chart, labels_chart]

    # Edge lines layer
    if all_edges:
        # Flatten edges into paired rows for line segments
        line_data: list[dict] = []
        for i, edge in enumerate(all_edges):
            etype = edge.get("edge_type", "unknown")
            line_data.append(
                {
                    "edge_id": i,
                    "x": edge["source_level"],
                    "y": edge["source_y"],
                    "edge_type": etype,
                },
            )
            line_data.append(
                {
                    "edge_id": i,
                    "x": edge["target_level"],
                    "y": edge["target_y"],
                    "edge_type": etype,
                },
            )

        edge_types_present = sorted({e["edge_type"] for e in all_edges})
        edge_color_domain = edge_types_present
        edge_color_range = [EDGE_COLORS.get(t, "#52525b") for t in edge_color_domain]

        edges_chart = (
            alt.Chart(alt.Data(values=line_data))
            .mark_line(opacity=0.4, strokeWidth=1.5)
            .encode(
                x=alt.X("x:Q"),
                y=alt.Y("y:Q"),
                detail="edge_id:N",
                color=alt.Color(
                    "edge_type:N",
                    scale=alt.Scale(domain=edge_color_domain, range=edge_color_range),
                    legend=alt.Legend(title="Edge Type"),
                ),
            )
        )
        layers.insert(0, edges_chart)  # Edges behind nodes

    # Determine reasonable height
    max_y = max((r["y_pos"] for r in all_records), default=5)
    chart_height = max(300, min(800, (max_y + 2) * 28))

    combined = (
        alt.layer(*layers)
        .properties(
            width="container",
            height=chart_height,
            title="Dependency Tree (left = depended by, right = depends on)",
        )
        .interactive()
    )

    return combined


def _build_node_detail_html(G: object, node_id: str) -> str:
    """Build HTML detail panel for a node.

    Args:
        G: NetworkX MultiDiGraph.
        node_id: Node ID to display details for.

    Returns:
        HTML string with node information.
    """
    if node_id not in G.nodes:
        return ""

    attrs = G.nodes[node_id]
    name = attrs.get("name", node_id)
    node_type = attrs.get("node_type", "unknown")
    file_path = attrs.get("file_path", "")
    line_start = attrs.get("line_start", "")
    line_end = attrs.get("line_end", "")

    in_deg = G.in_degree(node_id)
    out_deg = G.out_degree(node_id)

    # Collect edge type breakdown
    in_types: dict[str, int] = {}
    for _, _, k, _d in G.in_edges(node_id, keys=True, data=True):
        in_types[k] = in_types.get(k, 0) + 1

    out_types: dict[str, int] = {}
    for _, _, k, _d in G.out_edges(node_id, keys=True, data=True):
        out_types[k] = out_types.get(k, 0) + 1

    in_breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(in_types.items())) or "none"
    out_breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(out_types.items())) or "none"

    location = str(file_path)
    if line_start:
        location += f":{line_start}"
        if line_end and line_end != line_start:
            location += f"-{line_end}"

    return f"""
    <div style="background:#1e1e30; border:1px solid #333; border-radius:8px; padding:16px; color:#ccc;
                font-family:system-ui, sans-serif;">
      <h3 style="margin:0 0 12px 0; color:#eee;">{name}</h3>
      <table style="border-collapse:collapse; width:100%;">
        <tr><td style="padding:4px 8px; color:#888;">Type</td>
            <td style="padding:4px 8px;">{node_type}</td></tr>
        <tr><td style="padding:4px 8px; color:#888;">Location</td>
            <td style="padding:4px 8px; font-size:0.85em;">{location}</td></tr>
        <tr><td style="padding:4px 8px; color:#888;">In-degree</td>
            <td style="padding:4px 8px;">{in_deg} ({in_breakdown})</td></tr>
        <tr><td style="padding:4px 8px; color:#888;">Out-degree</td>
            <td style="padding:4px 8px;">{out_deg} ({out_breakdown})</td></tr>
      </table>
    </div>
    """


def build_dependencies_view(data: DashboardData) -> pn.viewable.Viewable:
    """Build the dependencies tab with symbol search, tree viz, and edge type filtering.

    Args:
        data: Dashboard data container with graph information.

    Returns:
        Panel Column layout with interactive dependency exploration.
    """
    import panel as pn

    # Handle missing graph
    if data.graph is None:
        return pn.pane.Markdown(
            "# Dependencies\n\nNo graph data available. Run `code-context-agent index` first.",
            sizing_mode="stretch_width",
        )

    G = data.graph._graph

    if G.number_of_nodes() == 0:
        return pn.pane.Markdown(
            "# Dependencies\n\nGraph is empty. Run `code-context-agent index` on a codebase first.",
            sizing_mode="stretch_width",
        )

    # Build name -> node_id lookup and autocomplete options
    name_to_id: dict[str, str] = {}
    for node_id in G.nodes:
        attrs = G.nodes[node_id]
        name = attrs.get("name", node_id)
        # Prefer shorter display name, but use full ID for disambiguation
        if name in name_to_id:
            # Disambiguate by appending file path
            existing_path = G.nodes[name_to_id[name]].get("file_path", "")
            new_path = attrs.get("file_path", "")
            name_to_id[f"{name} ({existing_path})"] = name_to_id.pop(name)
            name_to_id[f"{name} ({new_path})"] = node_id
        else:
            name_to_id[name] = node_id

    completions = sorted(name_to_id.keys())

    # Pick a default: the highest-degree node
    default_node_id = max(G.nodes, key=G.degree)
    default_name = G.nodes[default_node_id].get("name", default_node_id)
    # Find the display name in our lookup
    default_display = default_name
    for display_name, nid in name_to_id.items():
        if nid == default_node_id:
            default_display = display_name
            break

    # Widgets
    search_input = pn.widgets.AutocompleteInput(
        name="Symbol Search",
        options=completions,
        value=default_display,
        min_characters=1,
        case_sensitive=False,
        placeholder="Type a symbol name...",
        sizing_mode="stretch_width",
    )

    edge_filter = pn.widgets.CheckBoxGroup(
        name="Edge Types",
        options=_ALL_FILTERABLE_EDGE_TYPES,
        value=list(_DEFAULT_EDGE_TYPES),
        inline=True,
    )

    depth_slider = pn.widgets.IntSlider(
        name="Max Depth",
        start=1,
        end=6,
        value=4,
        step=1,
        width=200,
    )

    # Reactive update function
    def _update_view(symbol_name: str, edge_types: list[str], max_depth: int) -> pn.viewable.Viewable:
        node_id = name_to_id.get(symbol_name)
        if not node_id or node_id not in G.nodes:
            return pn.pane.Markdown(
                f"*Symbol '{symbol_name}' not found in the graph. Try typing a different name.*",
                sizing_mode="stretch_width",
            )

        et = frozenset(edge_types) if edge_types else None
        chart = _build_tree_chart(G, node_id, edge_types=et, max_depth=max_depth)
        detail_html = _build_node_detail_html(G, node_id)

        return pn.Column(
            pn.pane.HTML(detail_html, sizing_mode="stretch_width"),
            pn.pane.Vega(chart, sizing_mode="stretch_width"),
            sizing_mode="stretch_width",
        )

    bound_view = pn.bind(_update_view, search_input, edge_filter, depth_slider)

    header = pn.pane.Markdown(
        "# Dependencies\n\nExplore the dependency tree for any symbol. "
        "Outgoing edges (right) show what the symbol depends on; "
        "incoming edges (left) show what depends on it.",
        sizing_mode="stretch_width",
    )

    controls = pn.Row(
        search_input,
        depth_slider,
        sizing_mode="stretch_width",
    )

    return pn.Column(
        header,
        controls,
        pn.pane.Markdown("**Edge types to include:**", sizing_mode="stretch_width"),
        edge_filter,
        pn.layout.Divider(),
        bound_view,
        sizing_mode="stretch_width",
    )
