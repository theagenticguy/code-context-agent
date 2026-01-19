"""Progressive disclosure for code graph exploration.

This module provides the ProgressiveExplorer class for staged
exploration of code graphs, enabling AI agents to:
- Start with a high-level overview
- Progressively expand from interesting nodes
- Navigate by module or path
"""

from typing import Any

import networkx as nx

from .analysis import CodeAnalyzer
from .model import CodeGraph, EdgeType


class ProgressiveExplorer:
    """Staged exploration of code graph for AI context generation.

    Tracks what has been explored and suggests next steps for
    progressive disclosure of codebase structure.
    """

    def __init__(self, graph: CodeGraph, analyzer: CodeAnalyzer | None = None) -> None:
        """Initialize the explorer.

        Args:
            graph: The CodeGraph to explore
            analyzer: Optional CodeAnalyzer (created if not provided)
        """
        self.graph = graph
        self.analyzer = analyzer or CodeAnalyzer(graph)
        self.explored: set[str] = set()

    def get_overview(self) -> dict[str, Any]:
        """Get high-level codebase structure (Level 0).

        Provides entry points, hotspots, modules, and foundations
        for initial orientation.

        Returns:
            Dictionary with overview information
        """
        entry_points = self.analyzer.find_entry_points()[:5]
        hotspots = self.analyzer.find_hotspots(5)
        modules = self.analyzer.detect_modules()
        foundations = self.analyzer.find_foundations(5)

        # Mark overview nodes as explored
        for ep in entry_points:
            self.explored.add(ep["id"])
        for hs in hotspots:
            self.explored.add(hs["id"])
        for found in foundations:
            self.explored.add(found["id"])

        return {
            "total_nodes": self.graph.node_count,
            "total_edges": self.graph.edge_count,
            "entry_points": entry_points,
            "hotspots": hotspots,
            "modules": [
                {
                    "module_id": m["module_id"],
                    "size": m["size"],
                    "key_nodes": m["key_nodes"],
                    "cohesion": m["cohesion"],
                }
                for m in modules
            ],
            "foundations": foundations,
            "explored_count": len(self.explored),
        }

    def expand_node(self, node_id: str, depth: int = 1) -> dict[str, Any]:
        """Expand exploration from a specific node (Level 1+).

        Uses BFS to discover nodes within the specified depth.

        Args:
            node_id: The node to expand from
            depth: Number of hops to expand

        Returns:
            Dictionary with discovered nodes, edges, and suggestions
        """
        view = self.graph.get_view([EdgeType.CALLS, EdgeType.REFERENCES])

        if not view.has_node(node_id):
            return {"error": f"Node not found: {node_id}"}

        # BFS expansion
        try:
            distances = dict(nx.single_source_shortest_path_length(view, node_id, cutoff=depth))
        except nx.NetworkXError:
            distances = {node_id: 0}

        # Get the subgraph
        subgraph = view.subgraph(distances.keys())

        # Mark as explored
        self.explored.update(distances.keys())

        # Get node data
        discovered_nodes = []
        for n, dist in distances.items():
            node_data = self.graph.get_node_data(n) or {}
            discovered_nodes.append(
                {
                    "id": n,
                    "distance": dist,
                    **node_data,
                }
            )

        # Get edges
        edges = [{"source": u, "target": v, **d} for u, v, d in subgraph.edges(data=True)]

        # Suggest next nodes to explore (high-degree nodes not yet explored)
        suggested_next = self._suggest_next_exploration(view, distances)

        return {
            "center": node_id,
            "depth": depth,
            "discovered_nodes": discovered_nodes,
            "edges": edges,
            "suggested_next": suggested_next,
            "explored_count": len(self.explored),
        }

    def expand_module(self, module_id: int) -> dict[str, Any]:
        """Explore an entire detected module.

        Args:
            module_id: The module ID from detect_modules()

        Returns:
            Dictionary with module details and internal structure
        """
        modules = self.analyzer.detect_modules()

        if module_id >= len(modules):
            return {"error": f"Module not found: {module_id}"}

        module = modules[module_id]
        members = module["members"]

        # Mark module members as explored
        self.explored.update(members)

        # Get internal structure
        view = self.graph.get_view([EdgeType.CALLS, EdgeType.REFERENCES])
        subgraph = view.subgraph(members)

        # Detailed node info
        nodes = []
        for n in members:
            node_data = self.graph.get_node_data(n) or {}
            in_deg = subgraph.in_degree(n)
            out_deg = subgraph.out_degree(n)
            nodes.append(
                {
                    "id": n,
                    "in_degree": in_deg,
                    "out_degree": out_deg,
                    **node_data,
                }
            )

        # Sort by degree (most connected first)
        nodes.sort(key=lambda x: x["in_degree"] + x["out_degree"], reverse=True)

        # Internal edges
        edges = [{"source": u, "target": v, **d} for u, v, d in subgraph.edges(data=True)]

        # External connections (edges to/from outside the module)
        external_in = []
        external_out = []
        for member in members:
            for pred in view.predecessors(member):
                if pred not in members:
                    external_in.append({"from": pred, "to": member})
            for succ in view.successors(member):
                if succ not in members:
                    external_out.append({"from": member, "to": succ})

        return {
            "module_id": module_id,
            "size": len(members),
            "key_nodes": module["key_nodes"],
            "cohesion": module["cohesion"],
            "nodes": nodes[:20],  # Limit to top 20 by degree
            "edges": edges,
            "external_incoming": external_in[:10],
            "external_outgoing": external_out[:10],
            "explored_count": len(self.explored),
        }

    def get_path_between(self, source: str, target: str) -> dict[str, Any]:
        """Find shortest path between two nodes.

        Args:
            source: Source node ID
            target: Target node ID

        Returns:
            Dictionary with path information
        """
        view = self.graph.get_view()

        if not view.has_node(source):
            return {"error": f"Source node not found: {source}"}
        if not view.has_node(target):
            return {"error": f"Target node not found: {target}"}

        try:
            path = nx.shortest_path(view, source, target)
        except nx.NetworkXNoPath:
            return {"path": None, "message": "No path found between nodes"}

        # Mark path as explored
        self.explored.update(path)

        # Get node data along path
        path_nodes = []
        for i, n in enumerate(path):
            node_data = self.graph.get_node_data(n) or {}
            path_nodes.append({"id": n, "position": i, **node_data})

        # Get edges along path
        path_edges = []
        for i in range(len(path) - 1):
            edge_data = {}
            if view.has_edge(path[i], path[i + 1]):
                edge_data = dict(view[path[i]][path[i + 1]])
            path_edges.append({"source": path[i], "target": path[i + 1], **edge_data})

        return {
            "path": path,
            "length": len(path) - 1,
            "nodes": path_nodes,
            "edges": path_edges,
            "explored_count": len(self.explored),
        }

    def explore_category(self, category: str) -> dict[str, Any]:
        """Explore all nodes in a business logic category.

        Args:
            category: Category to explore (e.g., "db", "auth", "http")

        Returns:
            Dictionary with categorized nodes
        """
        matches = self.analyzer.find_clusters_by_category(category)

        # Mark as explored
        for m in matches:
            self.explored.add(m["id"])

        # Group by file
        by_file: dict[str, list[dict[str, Any]]] = {}
        for m in matches:
            file_path = m.get("file_path", "unknown")
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(m)

        return {
            "category": category,
            "total_count": len(matches),
            "files_count": len(by_file),
            "by_file": [{"file": f, "matches": m, "count": len(m)} for f, m in by_file.items()],
            "explored_count": len(self.explored),
        }

    def get_exploration_status(self) -> dict[str, Any]:
        """Get the current exploration status.

        Returns:
            Dictionary with exploration statistics
        """
        total = self.graph.node_count
        explored = len(self.explored)

        return {
            "total_nodes": total,
            "explored_nodes": explored,
            "unexplored_nodes": total - explored,
            "coverage_percent": (explored / total * 100) if total > 0 else 0,
        }

    def reset_exploration(self) -> None:
        """Reset exploration state to start fresh."""
        self.explored.clear()

    def _suggest_next_exploration(
        self,
        full_view: nx.DiGraph,
        current_distances: dict[str, int],
    ) -> list[dict[str, Any]]:
        """Suggest nodes to explore next.

        Prioritizes high-degree nodes at the edge of the current expansion
        that haven't been explored yet.

        Args:
            full_view: The full graph view
            current_distances: Distances from center

        Returns:
            List of suggested nodes with scores
        """
        max_dist = max(current_distances.values()) if current_distances else 0
        frontier = [n for n, d in current_distances.items() if d == max_dist]

        candidates: dict[str, float] = {}

        for node in frontier:
            for neighbor in full_view.successors(node):
                if neighbor not in self.explored:
                    # Score by degree in full graph
                    score = full_view.in_degree(neighbor) + full_view.out_degree(neighbor)
                    if neighbor not in candidates or candidates[neighbor] < score:
                        candidates[neighbor] = score

        # Sort by score and return top 5
        ranked = sorted(candidates.items(), key=lambda x: x[1], reverse=True)[:5]

        return [{"id": n, "score": s, **(self.graph.get_node_data(n) or {})} for n, s in ranked]
