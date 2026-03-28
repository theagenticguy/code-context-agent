import type { CodeGraph, GraphEdge, GraphNode } from '../types'

/** Shorten a file path to the last 3 segments. */
export function shortPath(fp: string): string {
  if (!fp) return ''
  const parts = fp.replace(/\\/g, '/').split('/')
  return parts.length <= 3 ? fp : `…/${parts.slice(-3).join('/')}`
}

/** Filter a graph by active node/edge types. Returns a new graph object. */
export function filterGraph(
  graph: CodeGraph,
  activeNodeTypes: Set<string>,
  activeEdgeTypes: Set<string>,
): { nodes: GraphNode[]; links: GraphEdge[] } {
  const nodes = graph.nodes.filter((n) => activeNodeTypes.has(n.node_type))
  const nodeIds = new Set(nodes.map((n) => n.id))
  const links = graph.links.filter(
    (e) => activeEdgeTypes.has(e.edge_type) && nodeIds.has(e.source) && nodeIds.has(e.target),
  )
  return { nodes, links }
}

/** Group nodes into modules by file path prefix (top 3 segments). */
export function detectModules(graph: { nodes: GraphNode[]; links: GraphEdge[] }): Array<{
  name: string
  members: GraphNode[]
}> {
  const groups = new Map<string, GraphNode[]>()

  for (const node of graph.nodes) {
    const parts = (node.file_path || '').replace(/\\/g, '/').split('/')
    const prefix = parts.slice(0, Math.min(3, parts.length - 1)).join('/') || '(root)'
    if (!groups.has(prefix)) groups.set(prefix, [])
    groups.get(prefix)?.push(node)
  }

  return Array.from(groups.entries())
    .map(([name, members]) => ({ name, members }))
    .sort((a, b) => b.members.length - a.members.length)
}

/** Compute degree centrality for all nodes. */
export function computeDegreeCentrality(graph: CodeGraph) {
  const inDeg = new Map<string, number>()
  const outDeg = new Map<string, number>()

  for (const e of graph.links) {
    outDeg.set(e.source, (outDeg.get(e.source) || 0) + 1)
    inDeg.set(e.target, (inDeg.get(e.target) || 0) + 1)
  }

  return graph.nodes
    .map((n) => ({
      ...n,
      inDegree: inDeg.get(n.id) || 0,
      outDegree: outDeg.get(n.id) || 0,
      totalDegree: (inDeg.get(n.id) || 0) + (outDeg.get(n.id) || 0),
    }))
    .sort((a, b) => b.totalDegree - a.totalDegree)
}

/** Find entry points: nodes with high out-degree and low in-degree. */
export function findEntryPoints(graph: CodeGraph) {
  const ranked = computeDegreeCentrality(graph)
  return ranked
    .filter((n) => n.outDegree > 0 && n.inDegree <= 1)
    .sort((a, b) => b.outDegree - a.outDegree)
    .slice(0, 20)
}

/** Build a hierarchy from nodes grouped by file path for circle packing. */
export function buildHierarchy(nodes: GraphNode[]) {
  const root: { name: string; children: unknown[] } = { name: 'root', children: [] }
  const groups = new Map<string, GraphNode[]>()

  for (const node of nodes) {
    const dir = node.file_path.replace(/\\/g, '/').split('/').slice(0, -1).join('/') || '(root)'
    if (!groups.has(dir)) groups.set(dir, [])
    groups.get(dir)?.push(node)
  }

  for (const [dir, members] of groups) {
    root.children.push({
      name: dir,
      children: members.map((m) => ({
        name: m.name,
        value: 1,
        node: m,
      })),
    })
  }

  return root
}
