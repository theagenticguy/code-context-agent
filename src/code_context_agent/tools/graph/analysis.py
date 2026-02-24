"""Graph analysis algorithms for code understanding.

This module provides the CodeAnalyzer class with methods for:
- Centrality analysis (hotspots, foundations, entry points)
- Clustering (community detection, pattern-based grouping)
- Proximity/similarity analysis
"""

from typing import Any

import networkx as nx

from .model import CodeGraph, EdgeType


class CodeAnalyzer:
    """Analyzer for code graphs using NetworkX algorithms.

    Provides methods for finding important code (centrality),
    detecting logical modules (clustering), and analyzing
    relationships between code elements.
    """

    def __init__(self, graph: CodeGraph) -> None:
        """Initialize the analyzer with a code graph.

        Args:
            graph: The CodeGraph to analyze
        """
        self.graph = graph

    def find_hotspots(self, top_k: int = 10) -> list[dict[str, Any]]:
        """Find code hotspots using betweenness centrality.

        Hotspots are code elements that lie on many shortest paths
        between other elements - they are often bottlenecks or
        central integration points.

        Args:
            top_k: Number of top hotspots to return

        Returns:
            List of dictionaries with node info and betweenness score
        """
        view = self.graph.get_view([EdgeType.CALLS, EdgeType.REFERENCES])

        if view.number_of_nodes() == 0:
            return []

        try:
            betweenness = nx.betweenness_centrality(view, weight="weight")
        except nx.NetworkXError:
            return []

        return self._format_ranked_results(betweenness, top_k)

    def find_foundations(self, top_k: int = 10) -> list[dict[str, Any]]:
        """Find foundational code using PageRank.

        Foundations are code elements that are heavily depended upon
        by other important code - the core infrastructure.

        Args:
            top_k: Number of top foundations to return

        Returns:
            List of dictionaries with node info and PageRank score
        """
        view = self.graph.get_view([EdgeType.CALLS, EdgeType.IMPORTS])

        if view.number_of_nodes() == 0:
            return []

        try:
            pagerank = nx.pagerank(view, alpha=0.85, weight="weight")
        except nx.NetworkXError:
            return []

        return self._format_ranked_results(pagerank, top_k)

    def find_trusted_foundations(
        self,
        seed_nodes: list[str] | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Find foundational code using TrustRank (noise-resistant PageRank).

        TrustRank propagates trust from seed nodes, making it more resistant
        to noise than standard PageRank. If no seed nodes provided, uses
        entry points as seeds.

        Args:
            seed_nodes: List of trusted node IDs (defaults to entry points)
            top_k: Number of top results to return

        Returns:
            List of dictionaries with node info and trust score
        """
        view = self.graph.get_view([EdgeType.CALLS, EdgeType.IMPORTS])

        if view.number_of_nodes() == 0:
            return []

        # Use entry points as default seeds
        if not seed_nodes:
            entry_points = self.find_entry_points()
            seed_nodes = [ep["id"] for ep in entry_points[:5]]

        if not seed_nodes:
            return self.find_foundations(top_k)

        # Build personalization dict for TrustRank
        trust = dict.fromkeys(view.nodes(), 0.0)
        for seed in seed_nodes:
            if seed in trust:
                trust[seed] = 1.0 / len(seed_nodes)

        try:
            scores = nx.pagerank(view, alpha=0.85, personalization=trust, weight="weight")
        except nx.NetworkXError:
            return []

        return self._format_ranked_results(scores, top_k)

    def find_entry_points(self) -> list[dict[str, Any]]:
        """Find likely entry points in the code.

        Entry points are nodes with no incoming call edges but
        outgoing calls - they initiate execution flow.

        Returns:
            List of dictionaries with entry point node info
        """
        view = self.graph.get_view([EdgeType.CALLS])

        entry_points = []
        for node in view.nodes():
            in_deg = view.in_degree(node)
            out_deg = view.out_degree(node)

            # Entry point: no callers but makes calls
            if in_deg == 0 and out_deg > 0:
                node_data = self.graph.get_node_data(node)
                entry_points.append(
                    {
                        "id": node,
                        "out_degree": out_deg,
                        **(node_data or {}),
                    },
                )

        # Also check for main/run/start patterns
        for node, data in self.graph.nodes(data=True):
            name = str(data.get("name", "")).lower()
            if any(p in name for p in ("main", "__main__", "run", "start", "app", "cli")):
                if not any(ep["id"] == node for ep in entry_points):
                    entry_points.append(
                        {
                            "id": node,
                            "out_degree": view.out_degree(node) if view.has_node(node) else 0,
                            **data,
                        },
                    )

        # Sort by out_degree (more calls = more significant entry point)
        entry_points.sort(key=lambda x: x.get("out_degree", 0), reverse=True)

        return entry_points

    def detect_modules(self, resolution: float = 1.0) -> list[dict[str, Any]]:
        """Detect logical modules using Louvain community detection.

        Uses the Louvain algorithm to find communities of densely
        connected code elements.

        Args:
            resolution: Clustering resolution (< 1 = larger clusters, > 1 = smaller)

        Returns:
            List of module dictionaries with members and metrics
        """
        view = self.graph.get_view([EdgeType.CALLS, EdgeType.IMPORTS])

        if view.number_of_nodes() < 2:
            return []

        # Louvain requires undirected graph
        undirected = view.to_undirected()

        try:
            # Try Leiden first (better community quality, requires backend)
            communities = nx.community.leiden_communities(undirected, resolution=resolution, seed=42)
        except (NotImplementedError, nx.NetworkXError, ValueError, RuntimeError):
            try:
                # Fallback to Louvain (pure NetworkX)
                communities = nx.community.louvain_communities(undirected, resolution=resolution, seed=42)
            except (nx.NetworkXError, ValueError, RuntimeError):
                return []

        modules = []
        for i, community in enumerate(communities):
            community_list = list(community)

            # Get key nodes (highest PageRank within community)
            subgraph = view.subgraph(community_list)
            if subgraph.number_of_nodes() > 0:
                try:
                    local_pr = nx.pagerank(subgraph)
                    key_nodes = sorted(local_pr.items(), key=lambda x: x[1], reverse=True)[:3]
                except (nx.NetworkXError, ValueError, RuntimeError):
                    key_nodes = [(n, 0) for n in community_list[:3]]
            else:
                key_nodes = []

            # Calculate cohesion (internal/external edge ratio)
            cohesion = self._calculate_cohesion(view, community)

            modules.append(
                {
                    "module_id": i,
                    "size": len(community_list),
                    "key_nodes": [{"id": n, "score": s} for n, s in key_nodes],
                    "members": community_list,
                    "cohesion": cohesion,
                },
            )

        # Sort by size (largest modules first)
        modules.sort(key=lambda x: x["size"], reverse=True)

        return modules

    def find_clusters_by_pattern(self, rule_id: str) -> list[dict[str, Any]]:
        """Find clusters of nodes matching a specific AST-grep rule.

        Groups nodes by their rule_id metadata to find related
        business logic patterns.

        Args:
            rule_id: The rule identifier to filter by

        Returns:
            List of matching nodes grouped by file
        """
        matching_nodes: dict[str, list[dict[str, Any]]] = {}

        for node_id, data in self.graph.nodes(data=True):
            if data.get("rule_id") == rule_id:
                file_path = data.get("file_path", "unknown")
                if file_path not in matching_nodes:
                    matching_nodes[file_path] = []
                matching_nodes[file_path].append({"id": node_id, **data})

        return [{"file": f, "matches": m, "count": len(m)} for f, m in matching_nodes.items()]

    def find_clusters_by_category(self, category: str) -> list[dict[str, Any]]:
        """Find all nodes matching a business logic category.

        Args:
            category: Category to filter by (e.g., "db", "auth", "http")

        Returns:
            List of matching nodes with their locations
        """
        matches = []

        for node_id, data in self.graph.nodes(data=True):
            if data.get("category") == category:
                matches.append({"id": node_id, **data})

        return matches

    def find_triangles(self, top_k: int = 10) -> list[dict[str, Any]]:
        """Find tightly-coupled code triads using triangle detection.

        Triangles in the call/import graph indicate three pieces of code
        that all depend on each other — potential cohesion or coupling issues.

        Args:
            top_k: Maximum number of triangles to return

        Returns:
            List of triangle dictionaries with the three node IDs
        """
        view = self.graph.get_view([EdgeType.CALLS, EdgeType.IMPORTS])
        undirected = view.to_undirected()

        triangles = []
        try:
            for triangle in nx.enumerate_all_cliques(undirected):
                if len(triangle) == 3:
                    triangles.append(
                        {
                            "nodes": list(triangle),
                            "node_details": [{"id": n, **(self.graph.get_node_data(n) or {})} for n in triangle],
                        },
                    )
                    if len(triangles) >= top_k:
                        break
        except nx.NetworkXError:
            pass

        return triangles

    def get_similar_nodes(self, node_id: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Find nodes similar to a given node based on graph structure.

        Uses personalized PageRank to find nodes closely related
        to the target node.

        Args:
            node_id: The node to find similar nodes for
            top_k: Number of similar nodes to return

        Returns:
            List of similar nodes with similarity scores
        """
        view = self.graph.get_view()

        if not view.has_node(node_id):
            return []

        try:
            # Personalized PageRank with target node as seed
            ppr = nx.pagerank(view, personalization={node_id: 1}, alpha=0.85)
        except nx.NetworkXError:
            return []

        # Remove self, sort by score
        del ppr[node_id]
        ranked = sorted(ppr.items(), key=lambda x: x[1], reverse=True)[:top_k]

        return [{"id": n, "similarity": s, **(self.graph.get_node_data(n) or {})} for n, s in ranked if s > 0]

    def calculate_coupling(self, node_a: str, node_b: str) -> dict[str, Any]:
        """Calculate coupling strength between two nodes.

        Considers shared neighbors, direct edges, and path length.

        Args:
            node_a: First node ID
            node_b: Second node ID

        Returns:
            Dictionary with coupling metrics
        """
        view = self.graph.get_view()

        if not view.has_node(node_a) or not view.has_node(node_b):
            return {"error": "Node not found", "coupling": 0.0}

        # Direct edge count
        direct_edges = 0
        if view.has_edge(node_a, node_b):
            direct_edges += 1
        if view.has_edge(node_b, node_a):
            direct_edges += 1

        # Shared neighbors
        neighbors_a = set(view.successors(node_a)) | set(view.predecessors(node_a))
        neighbors_b = set(view.successors(node_b)) | set(view.predecessors(node_b))
        shared = neighbors_a & neighbors_b

        # Shortest path length
        try:
            path_length = nx.shortest_path_length(view.to_undirected(), node_a, node_b)
        except nx.NetworkXNoPath:
            path_length = float("inf")

        # Calculate coupling score (higher = more coupled)
        coupling = direct_edges * 2.0 + len(shared) * 0.5 + (1.0 / (path_length + 1))

        return {
            "node_a": node_a,
            "node_b": node_b,
            "direct_edges": direct_edges,
            "shared_neighbors": len(shared),
            "path_length": path_length if path_length != float("inf") else None,
            "coupling": coupling,
        }

    def get_dependency_chain(self, node_id: str, direction: str = "outgoing", max_depth: int = 5) -> dict[str, Any]:
        """Get the dependency chain from/to a node.

        Args:
            node_id: Starting node
            direction: "outgoing" (what this depends on) or "incoming" (what depends on this)
            max_depth: Maximum depth to traverse

        Returns:
            Dictionary with nodes and edges in the chain
        """
        view = self.graph.get_view([EdgeType.CALLS, EdgeType.IMPORTS])

        if not view.has_node(node_id):
            return {"error": "Node not found"}

        if direction == "outgoing":
            nodes = dict(nx.single_source_shortest_path_length(view, node_id, cutoff=max_depth))
        else:
            # Incoming: traverse reverse graph
            reverse = view.reverse()
            nodes = dict(nx.single_source_shortest_path_length(reverse, node_id, cutoff=max_depth))

        # Get edges within the discovered nodes
        subgraph = view.subgraph(nodes.keys())
        edges = list(subgraph.edges(data=True))

        return {
            "root": node_id,
            "direction": direction,
            "depth": max_depth,
            "nodes": [{"id": n, "distance": d, **(self.graph.get_node_data(n) or {})} for n, d in nodes.items()],
            "edges": [{"source": u, "target": v, **d} for u, v, d in edges],
        }

    def _format_ranked_results(
        self,
        scores: dict[str, float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Format centrality results as ranked list.

        Args:
            scores: Dictionary of node IDs to scores
            top_k: Number of results to return

        Returns:
            List of dictionaries with node info and score
        """
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for node_id, score in ranked:
            node_data = self.graph.get_node_data(node_id)
            results.append({"id": node_id, "score": score, **(node_data or {})})

        return results

    def _calculate_cohesion(self, view: nx.DiGraph, community: set[str]) -> float:
        """Calculate cohesion of a community (internal/external edge ratio).

        Args:
            view: Graph view to analyze
            community: Set of node IDs in the community

        Returns:
            Cohesion score (higher = more cohesive)
        """
        internal_edges = 0
        external_edges = 0

        for u, v in view.edges():
            u_in = u in community
            v_in = v in community

            if u_in and v_in:
                internal_edges += 1
            elif u_in or v_in:
                external_edges += 1

        if external_edges == 0:
            return float("inf") if internal_edges > 0 else 0.0

        return internal_edges / external_edges
