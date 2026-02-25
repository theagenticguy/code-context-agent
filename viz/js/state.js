/**
 * Shared application state.
 *
 * Holds the loaded data and provides typed accessors.
 * All views read from this module; only the data loader writes to it.
 */

// ── Node / Edge type color maps ──────────────────────────────────
export const NODE_COLORS = {
  file:          '#3b82f6',
  class:         '#a78bfa',
  function:      '#34d399',
  method:        '#22d3ee',
  variable:      '#fbbf24',
  module:        '#f472b6',
  pattern_match: '#fb7185',
};

export const EDGE_COLORS = {
  calls:      '#6366f1',
  imports:    '#3b82f6',
  references: '#6a6a86',
  contains:   '#2a2a44',
  inherits:   '#a78bfa',
  implements: '#22d3ee',
  tests:      '#34d399',
  cochanges:  '#fbbf24',
};

export const SEVERITY_COLORS = {
  high:   '#ef4444',
  medium: '#f59e0b',
  low:    '#22c55e',
};

/** Edge types that represent actual code dependencies (not structural containment) */
export const DEPENDENCY_EDGE_TYPES = new Set(['calls', 'imports', 'inherits', 'implements']);

// ── Shared Tooltip ──────────────────────────────────────────────
let _tooltipEl = null;

export function showTooltip(event, html) {
  if (!_tooltipEl) {
    _tooltipEl = document.createElement('div');
    _tooltipEl.className = 'viz-tooltip';
    document.body.appendChild(_tooltipEl);
  }
  _tooltipEl.innerHTML = html;
  _tooltipEl.style.display = 'block';
  // Position with boundary checking
  const rect = _tooltipEl.getBoundingClientRect();
  let x = event.clientX + 14;
  let y = event.clientY - 10;
  if (x + rect.width > window.innerWidth - 12) x = event.clientX - rect.width - 14;
  if (y + rect.height > window.innerHeight - 12) y = window.innerHeight - rect.height - 12;
  if (y < 8) y = 8;
  _tooltipEl.style.left = x + 'px';
  _tooltipEl.style.top = y + 'px';
}

export function hideTooltip() {
  if (_tooltipEl) _tooltipEl.style.display = 'none';
}

// ── Mutable state ────────────────────────────────────────────────
export const state = {
  /** @type {{ nodes: any[], links: any[] } | null} */
  graph: null,

  /** @type {string | null} */
  narrative: null,

  /** @type {object | null} */
  analysisResult: null,

  /** Computed caches */
  nodeTypes: {},
  edgeTypes: {},
  nodeIndex: new Map(),

  /** Active view name */
  activeView: 'landing',
};

// ── Helpers ──────────────────────────────────────────────────────
/** Parse NetworkX node_link_data JSON into { nodes, links } for D3 */
export function parseGraphData(raw) {
  const nodes = (raw.nodes || []).map(n => ({
    id: n.id,
    name: n.name || n.id,
    nodeType: n.node_type || 'unknown',
    filePath: n.file_path || '',
    lineStart: n.line_start ?? 0,
    lineEnd: n.line_end ?? 0,
    metadata: { ...n },
  }));

  // Handle both "links" and "edges" keys (NetworkX format difference)
  const rawEdges = raw.links || raw.edges || [];
  const links = rawEdges.map(e => ({
    source: e.source,
    target: e.target,
    edgeType: e.edge_type || e.key || 'unknown',
    weight: e.weight || 1,
    metadata: { ...e },
  }));

  return { nodes, links };
}

/** Compute derived caches from loaded graph */
export function computeCaches() {
  if (!state.graph) return;

  // Node type counts
  state.nodeTypes = {};
  state.nodeIndex = new Map();
  for (const n of state.graph.nodes) {
    state.nodeTypes[n.nodeType] = (state.nodeTypes[n.nodeType] || 0) + 1;
    state.nodeIndex.set(n.id, n);
  }

  // Edge type counts
  state.edgeTypes = {};
  for (const e of state.graph.links) {
    state.edgeTypes[e.edgeType] = (state.edgeTypes[e.edgeType] || 0) + 1;
  }
}

/** Build an adjacency structure for fast neighbor lookup */
export function buildAdjacency() {
  if (!state.graph) return { outgoing: new Map(), incoming: new Map() };

  const outgoing = new Map();
  const incoming = new Map();

  for (const link of state.graph.links) {
    const sid = typeof link.source === 'object' ? link.source.id : link.source;
    const tid = typeof link.target === 'object' ? link.target.id : link.target;

    if (!outgoing.has(sid)) outgoing.set(sid, []);
    outgoing.get(sid).push({ target: tid, edge: link });

    if (!incoming.has(tid)) incoming.set(tid, []);
    incoming.get(tid).push({ source: sid, edge: link });
  }

  return { outgoing, incoming };
}

/** Calculate simple degree centrality (approximate hotspots) */
export function computeDegreeCentrality() {
  if (!state.graph) return [];
  const { outgoing, incoming } = buildAdjacency();

  return state.graph.nodes.map(n => {
    const out = (outgoing.get(n.id) || []).length;
    const inc = (incoming.get(n.id) || []).length;
    return { ...n, inDegree: inc, outDegree: out, totalDegree: inc + out };
  }).sort((a, b) => b.totalDegree - a.totalDegree);
}

/** Simple community detection by shared file path prefix */
export function detectSimpleModules() {
  if (!state.graph) return [];

  const groups = new Map();
  for (const n of state.graph.nodes) {
    // Group by directory (first two path segments after common prefix)
    const parts = n.filePath.split('/').filter(Boolean);
    const key = parts.slice(0, Math.min(3, parts.length - 1)).join('/') || 'root';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(n);
  }

  return Array.from(groups.entries())
    .map(([path, members], i) => ({
      module_id: i,
      path,
      size: members.length,
      members,
    }))
    .sort((a, b) => b.size - a.size);
}

/** Get entry points — nodes with no incoming dependency edges but outgoing ones.
 *  Falls back to top-level containers when no dependency edges exist. */
export function findEntryPoints() {
  if (!state.graph) return [];
  const { outgoing, incoming } = buildAdjacency();

  // Check if the graph has any dependency (non-contains) edges
  const hasDependencyEdges = state.graph.links.some(l => DEPENDENCY_EDGE_TYPES.has(l.edgeType));

  if (!hasDependencyEdges) {
    // Fallback: show containment roots (nodes with outgoing contains but no incoming contains).
    // These are top-level files, modules, or classes that contain other symbols.
    return state.graph.nodes.filter(n => {
      const inc = (incoming.get(n.id) || []).filter(e => e.edge.edgeType === 'contains');
      const out = (outgoing.get(n.id) || []).filter(e => e.edge.edgeType === 'contains');
      return inc.length === 0 && out.length > 0;
    }).map(n => ({
      ...n,
      outDegree: (outgoing.get(n.id) || []).filter(e => e.edge.edgeType === 'contains').length,
      entryReason: 'top-level',
    })).sort((a, b) => b.outDegree - a.outDegree).slice(0, 20);
  }

  return state.graph.nodes.filter(n => {
    if (!['function', 'method', 'class'].includes(n.nodeType)) return false;
    const inc = (incoming.get(n.id) || []).filter(e => DEPENDENCY_EDGE_TYPES.has(e.edge.edgeType));
    const out = (outgoing.get(n.id) || []).filter(e => DEPENDENCY_EDGE_TYPES.has(e.edge.edgeType));
    return inc.length === 0 && out.length > 0;
  }).map(n => ({
    ...n,
    outDegree: (outgoing.get(n.id) || []).filter(e => DEPENDENCY_EDGE_TYPES.has(e.edge.edgeType)).length,
    entryReason: 'dependency',
  })).sort((a, b) => b.outDegree - a.outDegree).slice(0, 20);
}
