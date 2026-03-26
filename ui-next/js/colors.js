// colors.js — Node, edge, and severity color maps

/** Default colors for known node types. Unknown types get the fallback. */
export const NODE_COLORS = {
  file: '#60a5fa',
  class: '#a78bfa',
  function: '#34d399',
  method: '#22d3ee',
  variable: '#fbbf24',
  module: '#f472b6',
  pattern_match: '#fb923c',
  unknown: '#6a6a86',
};

/** Default colors for known edge types. Unknown types get the fallback. */
export const EDGE_COLORS = {
  calls: '#c4b5fd',
  imports: '#93c5fd',
  references: '#a1a1aa',
  contains: '#71717a',
  inherits: '#d8b4fe',
  implements: '#67e8f9',
  tests: '#6ee7b7',
  cochanges: '#fde68a',
  similar_to: '#fb923c',
  unknown: '#52525b',
};

export const SEVERITY_COLORS = {
  high: '#f87171',
  medium: '#fbbf24',
  low: '#4ade80',
};

export const DEPENDENCY_EDGE_TYPES = new Set([
  'calls', 'imports', 'inherits', 'implements',
]);

/** Fallback color for any unrecognized node/edge type */
export const FALLBACK_COLOR = '#6a6a86';

/**
 * Get color for a node type, with fallback.
 * @param {string} type
 * @returns {string}
 */
export function nodeColor(type) {
  return NODE_COLORS[type] || FALLBACK_COLOR;
}

/**
 * Get color for an edge type, with fallback.
 * @param {string} type
 * @returns {string}
 */
export function edgeColor(type) {
  return EDGE_COLORS[type] || FALLBACK_COLOR;
}

/**
 * Get color for a severity level, with fallback.
 * @param {string} severity
 * @returns {string}
 */
export function severityColor(severity) {
  return SEVERITY_COLORS[severity] || '#6a6a86';
}

/** Node type display labels (for UI legends and filters) */
export const NODE_TYPE_LABELS = {
  file: 'Files',
  class: 'Classes',
  function: 'Functions',
  method: 'Methods',
  variable: 'Variables',
  module: 'Modules',
  pattern_match: 'Patterns',
};

/** Edge type display labels */
export const EDGE_TYPE_LABELS = {
  calls: 'Calls',
  imports: 'Imports',
  references: 'References',
  contains: 'Contains',
  inherits: 'Inherits',
  implements: 'Implements',
  tests: 'Tests',
  cochanges: 'Co-changes',
  similar_to: 'Similar',
};
