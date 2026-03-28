export const NODE_COLORS: Record<string, string> = {
  file: '#60a5fa',
  class: '#a78bfa',
  function: '#34d399',
  method: '#22d3ee',
  variable: '#fbbf24',
  module: '#f472b6',
  pattern_match: '#fb923c',
  unknown: '#6a6a86',
}

export const EDGE_COLORS: Record<string, string> = {
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
}

export const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f87171',
  medium: '#fbbf24',
  low: '#4ade80',
}

export const FALLBACK_COLOR = '#6a6a86'

export const NODE_TYPE_LABELS: Record<string, string> = {
  file: 'Files',
  class: 'Classes',
  function: 'Functions',
  method: 'Methods',
  variable: 'Variables',
  module: 'Modules',
  pattern_match: 'Patterns',
}

export const EDGE_TYPE_LABELS: Record<string, string> = {
  calls: 'Calls',
  imports: 'Imports',
  references: 'References',
  contains: 'Contains',
  inherits: 'Inherits',
  implements: 'Implements',
  tests: 'Tests',
  cochanges: 'Co-changes',
  similar_to: 'Similar',
}

export function nodeColor(type: string): string {
  return NODE_COLORS[type] ?? FALLBACK_COLOR
}

export function edgeColor(type: string): string {
  return EDGE_COLORS[type] ?? FALLBACK_COLOR
}

export function severityColor(severity: string): string {
  return SEVERITY_COLORS[severity] ?? FALLBACK_COLOR
}
