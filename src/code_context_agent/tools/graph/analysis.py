"""Graph analysis algorithms for code understanding.

This module provides the CodeAnalyzer class with methods for:
- Centrality analysis (hotspots, foundations, entry points)
- Clustering (community detection, pattern-based grouping)
- Proximity/similarity analysis
"""

import re
from collections import deque
from typing import Any

import networkx as nx

from .model import CodeGraph, EdgeType, NodeType


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

    def find_entry_points(self, framework_patterns: list | None = None) -> list[dict[str, Any]]:
        """Find likely entry points in the code.

        Entry points are nodes with no incoming call edges but
        outgoing calls - they initiate execution flow. When framework_patterns
        are provided, matching nodes receive a score boost.

        Args:
            framework_patterns: Optional list of FrameworkPattern objects for scoring boost.

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

        # Apply framework-specific scoring boost
        if framework_patterns:
            from code_context_agent.tools.graph.frameworks import score_entry_point

            for ep in entry_points:
                node_data = self.graph.get_node_data(ep["id"]) or {}
                boost = score_entry_point(node_data, framework_patterns)
                ep["score"] = ep.get("score", 1.0) * boost
                if boost > 1.0:
                    ep["framework_boost"] = boost

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
            pass  # graph structure doesn't support triangle detection (e.g. directed)

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

    def find_unused_symbols(
        self,
        node_types: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Find symbols with zero incoming cross-file references.

        Identifies functions, classes, and methods that are defined but
        never referenced from other files — dead code candidates.

        Args:
            node_types: Filter to specific types (default: function, class, method)
            exclude_patterns: Regex patterns to exclude from results

        Returns:
            List of unused symbol dicts with id, name, file_path, node_type
        """
        target_types = (
            set(node_types)
            if node_types
            else {
                NodeType.FUNCTION.value,
                NodeType.CLASS.value,
                NodeType.METHOD.value,
            }
        )
        default_excludes = [r"^test_", r"^_", r"__init__", r"__main__"]
        excludes = [re.compile(p) for p in (exclude_patterns or default_excludes)]

        view = self.graph.get_view([EdgeType.REFERENCES, EdgeType.CALLS, EdgeType.IMPORTS])

        unused = []
        for node_id, data in self.graph.nodes(data=True):
            if data.get("node_type") not in target_types:
                continue

            name = str(data.get("name", ""))
            if any(pat.search(name) for pat in excludes):
                continue

            node_file = data.get("file_path", "")
            if not node_file:
                continue

            # Count incoming edges from OTHER files
            cross_file_refs = 0
            if view.has_node(node_id):
                for pred in view.predecessors(node_id):
                    pred_data = self.graph.get_node_data(pred)
                    pred_file = (pred_data or {}).get("file_path", "")
                    if pred_file and pred_file != node_file:
                        cross_file_refs += 1
                        break  # One is enough to disqualify

            if cross_file_refs == 0:
                unused.append(
                    {
                        "id": node_id,
                        "name": name,
                        "file_path": node_file,
                        "node_type": data.get("node_type"),
                        "line_start": data.get("line_start", 0),
                    },
                )

        unused.sort(key=lambda x: (x["file_path"], x.get("line_start", 0)))
        return unused

    def find_refactoring_candidates(self, top_k: int = 10) -> list[dict[str, Any]]:
        """Identify refactoring opportunities by combining multiple signals.

        Combines:
        - Clone pairs (SIMILAR_TO edges) -> "extract shared helper"
        - Code smell pattern matches (rule_id contains "code_smell") -> structural issues
        - Unused symbols -> "dead code removal"

        Args:
            top_k: Maximum number of candidates to return

        Returns:
            Ranked list of refactoring candidates with type, files, and rationale.
        """
        candidates: list[dict[str, Any]] = []

        # 1. Clone groups from SIMILAR_TO edges
        similar_edges = self.graph.get_edges_by_type(EdgeType.SIMILAR_TO)
        clone_groups: dict[str, list[str]] = {}
        for source, target, data in similar_edges:
            key = f"{source}|{target}" if source < target else f"{target}|{source}"
            if key not in clone_groups:
                clone_groups[key] = [source, target]
                candidates.append(
                    {
                        "type": "extract_helper",
                        "pattern": f"Duplicate code between {source} and {target}",
                        "files": [source, target],
                        "occurrence_count": 2,
                        "duplicated_lines": int(data.get("duplicated_lines", 0)),
                        "score": int(data.get("duplicated_lines", 5)) * 2.0,
                    },
                )

        # 2. Code smell patterns
        smell_counts: dict[str, list[str]] = {}
        for node_id, data in self.graph.nodes(data=True):
            rule_id = data.get("rule_id", "")
            note = data.get("note", "")
            if "code_smell" in note or "code_smell" in rule_id:
                if rule_id not in smell_counts:
                    smell_counts[rule_id] = []
                smell_counts[rule_id].append(data.get("file_path", node_id))

        for rule_id, files in smell_counts.items():
            candidates.append(
                {
                    "type": "code_smell",
                    "pattern": rule_id,
                    "files": list(set(files)),
                    "occurrence_count": len(files),
                    "duplicated_lines": 0,
                    "score": len(files) * 1.5,
                },
            )

        # 3. Unused symbols
        unused = self.find_unused_symbols()
        if unused:
            # Group by file
            by_file: dict[str, list[str]] = {}
            for sym in unused:
                fp = sym["file_path"]
                if fp not in by_file:
                    by_file[fp] = []
                by_file[fp].append(sym["name"])

            for fp, names in by_file.items():
                candidates.append(
                    {
                        "type": "dead_code",
                        "pattern": f"{len(names)} unused symbol(s) in {fp}",
                        "files": [fp],
                        "occurrence_count": len(names),
                        "duplicated_lines": 0,
                        "score": len(names) * 1.0,
                    },
                )

        # Sort by score descending, return top_k
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]

    def blast_radius(
        self,
        node_id: str,
        max_depth: int = 5,
        top_k: int = 20,
    ) -> dict[str, Any]:
        """Compute the blast radius of changing a node.

        BFS outward from the target node through reverse edges (incoming callers,
        importers, references). Each hop increases distance and halves the impact
        score. Edge confidence is factored into the decay.

        Impact formula per affected node: 1 / (2^distance) * confidence_product

        Args:
            node_id: The node to analyze blast radius for.
            max_depth: Maximum BFS depth (hops) to trace.
            top_k: Maximum affected nodes to return.

        Returns:
            Dictionary with total_affected, risk_score, depth_histogram,
            and ranked affected_nodes list.
        """
        view = self.graph.get_view([EdgeType.CALLS, EdgeType.IMPORTS, EdgeType.REFERENCES])

        if not view.has_node(node_id):
            return {"error": f"Node not found: {node_id}"}

        # BFS on the reverse graph (who depends on this node?)
        reverse = view.reverse()

        # BFS with distance tracking and confidence accumulation
        # Each entry: (node, distance, cumulative_confidence)
        visited: dict[str, tuple[int, float]] = {}  # node -> (distance, impact)
        queue: deque[tuple[str, int, float]] = deque([(node_id, 0, 1.0)])
        visited[node_id] = (0, 1.0)

        while queue:
            current, dist, conf_product = queue.popleft()

            if dist >= max_depth:
                continue

            for neighbor in reverse.successors(current):
                if neighbor in visited:
                    continue

                edge_data = reverse.edges[current, neighbor]
                edge_conf = edge_data.get("confidence", 1.0)
                new_conf = conf_product * edge_conf
                new_dist = dist + 1
                impact = new_conf / (2**new_dist)

                visited[neighbor] = (new_dist, impact)
                queue.append((neighbor, new_dist, new_conf))

        # Remove the source node itself
        visited.pop(node_id, None)

        if not visited:
            return {
                "node_id": node_id,
                "total_affected": 0,
                "risk_score": 0.0,
                "depth_histogram": {},
                "affected_nodes": [],
            }

        # Build depth histogram
        depth_histogram: dict[int, int] = {}
        for _nid, (d, _impact) in visited.items():
            depth_histogram[d] = depth_histogram.get(d, 0) + 1

        # Rank by impact score
        ranked = sorted(visited.items(), key=lambda x: x[1][1], reverse=True)[:top_k]

        affected_nodes = []
        for nid, (d, impact) in ranked:
            nd = self.graph.get_node_data(nid) or {}
            affected_nodes.append(
                {
                    "id": nid,
                    "name": nd.get("name", nid),
                    "node_type": nd.get("node_type", "unknown"),
                    "file_path": nd.get("file_path", ""),
                    "distance": d,
                    "impact": round(impact, 6),
                },
            )

        # Risk score: sum of all impacts
        risk_score = sum(impact for _, (_, impact) in visited.items())

        return {
            "node_id": node_id,
            "total_affected": len(visited),
            "risk_score": round(risk_score, 4),
            "depth_histogram": dict(sorted(depth_histogram.items())),
            "affected_nodes": affected_nodes,
        }

    def diff_impact(
        self,
        changed_files: list[dict[str, Any]],
        max_depth: int = 3,
        top_k: int = 20,
    ) -> dict[str, Any]:
        """Map git diff changed lines to graph nodes and compute aggregate blast radius.

        For each changed file+line range, finds overlapping graph nodes (by file_path
        and line_start/line_end overlap). Runs blast_radius on each matched node,
        merges results, and suggests test files via TESTS edges.

        Args:
            changed_files: List of dicts with keys:
                - file_path (str): Relative path to the changed file.
                - lines (list[int]): Changed line numbers (1-indexed).
            max_depth: Max BFS depth for blast_radius per node.
            top_k: Max affected nodes to return in the merged result.

        Returns:
            Dictionary with directly_changed (matched nodes), total_affected,
            aggregate_risk, affected_nodes (merged, deduplicated), and suggested_tests.
        """
        if not changed_files:
            return {
                "directly_changed": [],
                "total_affected": 0,
                "aggregate_risk": 0.0,
                "affected_nodes": [],
                "suggested_tests": [],
            }

        # Step 1: Build file -> nodes index
        file_nodes: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for node_id, data in self.graph.nodes(data=True):
            fp = data.get("file_path", "")
            if fp:
                if fp not in file_nodes:
                    file_nodes[fp] = []
                file_nodes[fp].append((node_id, dict(data)))

        # Step 2: Match changed lines to graph nodes
        directly_changed: list[dict[str, Any]] = []
        matched_node_ids: set[str] = set()

        for change in changed_files:
            fp = change.get("file_path", "")
            lines = set(change.get("lines", []))
            if not fp or not lines:
                continue

            # Try exact path and also suffix matching (diff may use relative paths)
            candidates = file_nodes.get(fp, [])
            if not candidates:
                for stored_fp, nodes in file_nodes.items():
                    if stored_fp.endswith(fp) or fp.endswith(stored_fp):
                        candidates = nodes
                        break

            for node_id, data in candidates:
                line_start = data.get("line_start", 0)
                line_end = data.get("line_end", 0)
                if any(line_start <= line <= line_end for line in lines):
                    if node_id not in matched_node_ids:
                        matched_node_ids.add(node_id)
                        directly_changed.append(
                            {
                                "id": node_id,
                                "name": data.get("name", node_id),
                                "node_type": data.get("node_type", "unknown"),
                                "file_path": data.get("file_path", ""),
                                "line_start": line_start,
                                "line_end": line_end,
                            },
                        )

        # Step 3: Run blast_radius on each matched node and merge
        all_affected: dict[str, dict[str, Any]] = {}
        aggregate_risk = 0.0

        for node_info in directly_changed:
            br = self.blast_radius(node_info["id"], max_depth=max_depth, top_k=50)
            if "error" in br:
                continue
            aggregate_risk += br.get("risk_score", 0.0)
            for affected in br.get("affected_nodes", []):
                aid = affected["id"]
                if aid in matched_node_ids:
                    continue
                if aid not in all_affected or affected["impact"] > all_affected[aid]["impact"]:
                    all_affected[aid] = affected

        merged = sorted(all_affected.values(), key=lambda x: x["impact"], reverse=True)[:top_k]

        # Step 4: Suggest test files via TESTS edges
        test_edges = self.graph.get_edges_by_type(EdgeType.TESTS)
        suggested_tests: list[str] = []
        all_impacted = matched_node_ids | set(all_affected.keys())
        for source, target, _data in test_edges:
            if target in all_impacted and source not in suggested_tests:
                suggested_tests.append(source)

        return {
            "directly_changed": directly_changed,
            "total_affected": len(all_affected),
            "aggregate_risk": round(aggregate_risk, 4),
            "affected_nodes": merged,
            "suggested_tests": suggested_tests,
        }

    def trace_execution_flows(
        self,
        max_depth: int = 8,
        min_flow_length: int = 3,
        max_flows: int = 15,
    ) -> list[dict[str, Any]]:
        """Trace execution flows from entry points through CALLS edges.

        Identifies entry points and traces forward through the call graph to produce
        named execution flows. Each flow represents a path from an entry point to a
        leaf (no outgoing CALLS) or the max depth cutoff.

        Args:
            max_depth: Maximum call chain depth to trace.
            min_flow_length: Minimum number of nodes for a flow to be included.
            max_flows: Maximum number of flows to return.

        Returns:
            List of flow dicts sorted by score descending, each containing:
            flow_id, name, entry_point, length, path, nodes, score.
        """
        calls_view = self.graph.get_view([EdgeType.CALLS])

        if calls_view.number_of_nodes() == 0:
            return []

        # Get entry points, take top 10 by out-degree in calls view
        entry_points = self.find_entry_points()
        entry_points.sort(
            key=lambda ep: calls_view.out_degree(ep["id"]) if calls_view.has_node(ep["id"]) else 0,
            reverse=True,
        )
        entry_points = entry_points[:10]

        if not entry_points:
            return []

        # Collect all flows via iterative DFS from each entry point
        max_paths_per_entry = 5
        all_flows: list[list[str]] = []

        for ep in entry_points:
            ep_id = ep["id"]
            if not calls_view.has_node(ep_id):
                continue

            paths: list[list[str]] = []
            stack: list[tuple[str, list[str], set[str]]] = [(ep_id, [ep_id], {ep_id})]

            while stack and len(paths) < max_paths_per_entry:
                node, path, visited = stack.pop()

                successors = [s for s in calls_view.successors(node) if s not in visited]
                is_leaf = len(successors) == 0
                at_depth = len(path) > max_depth

                if is_leaf or at_depth:
                    paths.append(path)
                    continue

                for succ in successors:
                    stack.append((succ, [*path, succ], visited | {succ}))

            all_flows.extend(paths)

        # Filter by min length
        all_flows = [f for f in all_flows if len(f) >= min_flow_length]

        if not all_flows:
            return []

        # Deduplicate: remove flows that are strict prefixes of longer flows
        all_flows.sort(key=len, reverse=True)
        kept: list[list[str]] = []
        for flow in all_flows:
            is_prefix = False
            for longer in kept:
                if len(flow) < len(longer) and longer[: len(flow)] == flow:
                    is_prefix = True
                    break
            if not is_prefix:
                kept.append(flow)

        # Score: length * sum of degrees in calls view
        scored: list[tuple[list[str], float]] = []
        for flow in kept:
            degree_sum = sum(calls_view.degree(n) for n in flow if calls_view.has_node(n))
            score = len(flow) * degree_sum
            scored.append((flow, score))

        # Normalize scores
        max_score = max(s for _, s in scored) if scored else 1.0
        if max_score == 0:
            max_score = 1.0

        scored.sort(key=lambda x: x[1], reverse=True)
        scored = scored[:max_flows]

        # Build result dicts
        results: list[dict[str, Any]] = []
        for i, (path, score) in enumerate(scored):
            first_name = (self.graph.get_node_data(path[0]) or {}).get("name", path[0])
            last_name = (self.graph.get_node_data(path[-1]) or {}).get("name", path[-1])
            if len(path) > 2:
                name = f"{first_name} -> ... -> {last_name}"
            else:
                name = " -> ".join((self.graph.get_node_data(n) or {}).get("name", n) for n in path)

            nodes = []
            for nid in path:
                nd = self.graph.get_node_data(nid) or {}
                nodes.append(
                    {
                        "id": nid,
                        "name": nd.get("name", nid),
                        "node_type": nd.get("node_type", "unknown"),
                        "file_path": nd.get("file_path", ""),
                    },
                )

            results.append(
                {
                    "flow_id": i,
                    "name": name,
                    "entry_point": path[0],
                    "length": len(path),
                    "path": path,
                    "nodes": nodes,
                    "score": score / max_score,
                },
            )

        return results

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
