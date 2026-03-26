// graph-utils.js — Graph analysis algorithms for CodeGraph data

import { DEPENDENCY_EDGE_TYPES } from './colors.js';

/**
 * Parse raw NetworkX node_link_data JSON into a normalized CodeGraph.
 * Handles missing fields with sensible defaults.
 * @param {object} raw - Raw graph JSON from code_graph.json
 * @returns {object} Normalized CodeGraph
 */
export function parseGraph(raw) {
  return {
    directed: raw.directed,
    multigraph: raw.multigraph,
    graph: raw.graph,
    nodes: (raw.nodes || []).map((n) => ({
      id: n.id,
      name: n.name || n.id,
      node_type: n.node_type || 'unknown',
      file_path: n.file_path || '',
      line_start: n.line_start ?? 0,
      line_end: n.line_end ?? 0,
      lsp_kind: n.lsp_kind,
    })),
    links: (raw.links || []).map((e) => ({
      source: e.source,
      target: e.target,
      edge_type: e.edge_type || e.key || 'unknown',
      weight: e.weight || 1,
      confidence: e.confidence,
    })),
  };
}

/**
 * Build adjacency maps for fast neighbor lookup.
 * @param {object} graph - CodeGraph with nodes and links
 * @returns {{ outgoing: Map<string, Array<{target: string, edge: object}>>, incoming: Map<string, Array<{source: string, edge: object}>> }}
 */
export function buildAdjacency(graph) {
  const outgoing = new Map();
  const incoming = new Map();

  for (const link of graph.links) {
    if (!outgoing.has(link.source)) outgoing.set(link.source, []);
    outgoing.get(link.source).push({ target: link.target, edge: link });

    if (!incoming.has(link.target)) incoming.set(link.target, []);
    incoming.get(link.target).push({ source: link.source, edge: link });
  }

  return { outgoing, incoming };
}

/**
 * Count occurrences of each node type.
 * @param {Array<object>} nodes
 * @returns {Object<string, number>}
 */
export function countNodeTypes(nodes) {
  const counts = {};
  for (const n of nodes) {
    counts[n.node_type] = (counts[n.node_type] || 0) + 1;
  }
  return counts;
}

/**
 * Count occurrences of each edge type.
 * @param {Array<object>} edges
 * @returns {Object<string, number>}
 */
export function countEdgeTypes(edges) {
  const counts = {};
  for (const e of edges) {
    counts[e.edge_type] = (counts[e.edge_type] || 0) + 1;
  }
  return counts;
}

/**
 * Compute degree centrality for all nodes, sorted by total degree descending.
 * @param {object} graph - CodeGraph
 * @returns {Array<object>} Nodes augmented with inDegree, outDegree, totalDegree
 */
export function computeDegreeCentrality(graph) {
  const { outgoing, incoming } = buildAdjacency(graph);

  return graph.nodes
    .map((n) => ({
      ...n,
      inDegree: (incoming.get(n.id) || []).length,
      outDegree: (outgoing.get(n.id) || []).length,
      totalDegree:
        (incoming.get(n.id) || []).length +
        (outgoing.get(n.id) || []).length,
    }))
    .sort((a, b) => b.totalDegree - a.totalDegree);
}

/**
 * Detect modules by grouping nodes by file path prefix (top 3 segments).
 * @param {object} graph - CodeGraph
 * @returns {Array<{path: string, members: Array<object>, size: number}>}
 */
export function detectModules(graph) {
  const groups = new Map();

  for (const n of graph.nodes) {
    const parts = (n.file_path || '').split('/').filter(Boolean);
    const key =
      parts.slice(0, Math.min(3, parts.length - 1)).join('/') || 'root';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(n);
  }

  return Array.from(groups.entries())
    .map(([path, members]) => ({ path, members, size: members.length }))
    .sort((a, b) => b.size - a.size);
}

/**
 * Find entry points: nodes with no incoming dependency edges but outgoing ones.
 * Falls back to containment roots when no dependency edges exist.
 * @param {object} graph - CodeGraph
 * @returns {Array<object>} Up to 20 entry point nodes with outDegree
 */
export function findEntryPoints(graph) {
  const { outgoing, incoming } = buildAdjacency(graph);
  const hasDeps = graph.links.some((l) =>
    DEPENDENCY_EDGE_TYPES.has(l.edge_type)
  );

  if (!hasDeps) {
    // Fallback: containment roots
    return graph.nodes
      .filter((n) => {
        const inc = (incoming.get(n.id) || []).filter(
          (e) => e.edge.edge_type === 'contains'
        );
        const out = (outgoing.get(n.id) || []).filter(
          (e) => e.edge.edge_type === 'contains'
        );
        return inc.length === 0 && out.length > 0;
      })
      .map((n) => ({
        ...n,
        outDegree: (outgoing.get(n.id) || []).filter(
          (e) => e.edge.edge_type === 'contains'
        ).length,
        reason: 'top-level',
      }))
      .sort((a, b) => b.outDegree - a.outDegree)
      .slice(0, 20);
  }

  return graph.nodes
    .filter((n) => {
      if (!['function', 'method', 'class'].includes(n.node_type)) return false;
      const inc = (incoming.get(n.id) || []).filter((e) =>
        DEPENDENCY_EDGE_TYPES.has(e.edge.edge_type)
      );
      const out = (outgoing.get(n.id) || []).filter((e) =>
        DEPENDENCY_EDGE_TYPES.has(e.edge.edge_type)
      );
      return inc.length === 0 && out.length > 0;
    })
    .map((n) => ({
      ...n,
      outDegree: (outgoing.get(n.id) || []).filter((e) =>
        DEPENDENCY_EDGE_TYPES.has(e.edge.edge_type)
      ).length,
      reason: 'dependency',
    }))
    .sort((a, b) => b.outDegree - a.outDegree)
    .slice(0, 20);
}

/**
 * Shorten a file path to its last 3 segments.
 * @param {string} p - File path
 * @returns {string}
 */
export function shortPath(p) {
  if (!p) return '';
  return p.split('/').slice(-3).join('/');
}

/**
 * BFS dependency chain traversal from a starting node.
 * Only follows DEPENDENCY_EDGE_TYPES (calls, imports, inherits, implements).
 * @param {object} graph - CodeGraph
 * @param {string} nodeId - Starting node ID
 * @param {'downstream'|'upstream'} direction - Follow outgoing or incoming edges
 * @param {number} [maxDepth=5] - Maximum BFS depth
 * @returns {Array<{node: object, depth: number, edge: object}>}
 */
export function getDependencyChain(graph, nodeId, direction = 'downstream', maxDepth = 5) {
  const { outgoing, incoming } = buildAdjacency(graph);
  const nodeMap = new Map(graph.nodes.map((n) => [n.id, n]));
  const visited = new Set([nodeId]);
  const result = [];
  const queue = [{ id: nodeId, depth: 0 }];

  while (queue.length > 0) {
    const { id, depth } = queue.shift();
    if (depth >= maxDepth) continue;

    const neighbors = direction === 'downstream'
      ? (outgoing.get(id) || [])
      : (incoming.get(id) || []);

    for (const entry of neighbors) {
      if (!DEPENDENCY_EDGE_TYPES.has(entry.edge.edge_type)) continue;

      const neighborId = direction === 'downstream' ? entry.target : entry.source;
      if (visited.has(neighborId)) continue;

      visited.add(neighborId);
      const node = nodeMap.get(neighborId);
      if (node) {
        result.push({ node, depth: depth + 1, edge: entry.edge });
        queue.push({ id: neighborId, depth: depth + 1 });
      }
    }
  }

  return result;
}

/**
 * Filter a CodeGraph by node types, edge types, and search query.
 * @param {object} graph - CodeGraph
 * @param {object} options
 * @param {Set<string>} [options.nodeTypes] - Node types to include (empty = all)
 * @param {Set<string>} [options.edgeTypes] - Edge types to include (empty = all)
 * @param {string} [options.searchQuery] - Case-insensitive search against name/file_path
 * @returns {object} Filtered CodeGraph
 */
export function filterGraph(graph, { nodeTypes, edgeTypes, searchQuery } = {}) {
  let filteredNodes = graph.nodes;

  // Filter by node types
  if (nodeTypes && nodeTypes.size > 0) {
    filteredNodes = filteredNodes.filter((n) => nodeTypes.has(n.node_type));
  }

  // Filter by search query
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    filteredNodes = filteredNodes.filter(
      (n) =>
        (n.name && n.name.toLowerCase().includes(q)) ||
        (n.file_path && n.file_path.toLowerCase().includes(q))
    );
  }

  const nodeIds = new Set(filteredNodes.map((n) => n.id));

  // Filter links: both endpoints must be in the filtered node set
  let filteredLinks = graph.links.filter(
    (l) => nodeIds.has(l.source) && nodeIds.has(l.target)
  );

  // Filter by edge types
  if (edgeTypes && edgeTypes.size > 0) {
    filteredLinks = filteredLinks.filter((l) => edgeTypes.has(l.edge_type));
  }

  return {
    directed: graph.directed,
    multigraph: graph.multigraph,
    graph: graph.graph,
    nodes: filteredNodes,
    links: filteredLinks,
  };
}

/**
 * Build a d3-hierarchy-compatible tree from a flat graph.
 * Groups by file path segments: root > dir > dir > file > symbols.
 * @param {object} graph - CodeGraph
 * @returns {object} Tree root node with { name, children } structure
 */
export function buildHierarchy(graph) {
  const root = { name: 'root', children: [] };

  for (const node of graph.nodes) {
    const filePath = node.file_path || '';
    const parts = filePath.split('/').filter(Boolean);

    // Navigate/create the directory tree
    let current = root;
    for (const part of parts) {
      let child = current.children.find((c) => c.name === part && c.children);
      if (!child) {
        child = { name: part, children: [] };
        current.children.push(child);
      }
      current = child;
    }

    // Add the symbol as a leaf node (no children array = leaf)
    current.children.push({
      name: node.name,
      id: node.id,
      node_type: node.node_type,
      file_path: node.file_path,
      value: 1,
    });
  }

  // Recursively compute value for branch nodes
  function computeValue(n) {
    if (!n.children || n.children.length === 0) {
      return n.value || 1;
    }
    n.value = n.children.reduce((sum, c) => sum + computeValue(c), 0);
    return n.value;
  }
  computeValue(root);

  return root;
}
