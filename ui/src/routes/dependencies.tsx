import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { hierarchy, tree } from 'd3-hierarchy'
import { linkHorizontal } from 'd3-shape'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { EmptyState } from '../components/empty-state'
import { useTooltip } from '../components/tooltip'
import { edgeColor, nodeColor } from '../constants/colors'
import { shortPath } from '../lib/graph-utils'
import { useStore } from '../store/use-store'
import type { GraphEdge, GraphNode } from '../types'

export const Route = createFileRoute('/dependencies')({
  component: DependenciesView,
})

/** Edge types that represent dependency relationships (excludes structural 'contains' and correlation-based 'cochanges'/'similar_to'). */
const DEP_EDGE_TYPES = new Set([
  'imports',
  'calls',
  'inherits',
  'implements',
  'references',
  'tests',
  'type_reference',
  'uses',
])

interface TreeDatum {
  name: string
  nodeId: string
  nodeType: string
  filePath: string
  edgeType?: string
  children?: TreeDatum[]
}

function DependenciesView() {
  const graph = useStore((s) => s.graph)
  const setPendingSearch = useStore((s) => s.setPendingSearch)
  const navigate = useNavigate()
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const tooltip = useTooltip()

  const [query, setQuery] = useState('')
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [showDropdown, setShowDropdown] = useState(false)
  const [highlightIdx, setHighlightIdx] = useState(-1)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Observe container size
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) setDimensions({ width, height })
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // Build lookup maps
  const { nodeMap, outEdges, inEdges } = useMemo(() => {
    if (!graph)
      return {
        nodeMap: new Map<string, GraphNode>(),
        outEdges: new Map<string, GraphEdge[]>(),
        inEdges: new Map<string, GraphEdge[]>(),
      }

    const nm = new Map<string, GraphNode>()
    for (const n of graph.nodes) nm.set(n.id, n)

    const out = new Map<string, GraphEdge[]>()
    const inn = new Map<string, GraphEdge[]>()
    for (const e of graph.links) {
      if (!DEP_EDGE_TYPES.has(e.edge_type)) continue
      if (!out.has(e.source)) out.set(e.source, [])
      out.get(e.source)?.push(e)
      if (!inn.has(e.target)) inn.set(e.target, [])
      inn.get(e.target)?.push(e)
    }
    return { nodeMap: nm, outEdges: out, inEdges: inn }
  }, [graph])

  // Autocomplete matches
  const matches = useMemo(() => {
    if (!graph || !query.trim()) return []
    const q = query.toLowerCase()
    return graph.nodes.filter((n) => n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q)).slice(0, 10)
  }, [graph, query])

  // Build dependency tree for the selected node
  const treeDatum = useMemo((): TreeDatum | null => {
    if (!selectedNode) return null

    const visited = new Set<string>()

    function buildChildren(nodeId: string, direction: 'out' | 'in', depth: number): TreeDatum[] {
      if (depth > 4 || visited.has(nodeId)) return []
      visited.add(nodeId)

      const edges = direction === 'out' ? (outEdges.get(nodeId) ?? []) : (inEdges.get(nodeId) ?? [])
      const children: TreeDatum[] = []

      for (const edge of edges) {
        const targetId = direction === 'out' ? edge.target : edge.source
        const targetNode = nodeMap.get(targetId)
        if (!targetNode || visited.has(targetId)) continue

        const child: TreeDatum = {
          name: targetNode.name,
          nodeId: targetNode.id,
          nodeType: targetNode.node_type,
          filePath: targetNode.file_path,
          edgeType: edge.edge_type,
          children: buildChildren(targetId, direction, depth + 1),
        }
        children.push(child)
      }
      return children
    }

    // Build outgoing dependencies
    const outChildren = buildChildren(selectedNode.id, 'out', 0)
    // Reset visited for incoming
    visited.clear()
    visited.add(selectedNode.id)
    const inChildren = buildChildren(selectedNode.id, 'in', 0)

    const root: TreeDatum = {
      name: selectedNode.name,
      nodeId: selectedNode.id,
      nodeType: selectedNode.node_type,
      filePath: selectedNode.file_path,
      children: [
        ...(outChildren.length > 0
          ? [{ name: 'Depends On', nodeId: '__out__', nodeType: 'group', filePath: '', children: outChildren }]
          : []),
        ...(inChildren.length > 0
          ? [{ name: 'Depended By', nodeId: '__in__', nodeType: 'group', filePath: '', children: inChildren }]
          : []),
      ],
    }

    return root
  }, [selectedNode, outEdges, inEdges, nodeMap])

  // Layout the tree (skip if container hasn't been measured yet)
  const treeLayout = useMemo(() => {
    if (!treeDatum || dimensions.width === 0 || dimensions.height === 0) return null

    const root = hierarchy<TreeDatum>(treeDatum)
    const nodeCount = root.descendants().length
    const treeHeight = Math.max(dimensions.height - 40, nodeCount * 28)

    const layoutFn = tree<TreeDatum>().size([treeHeight, Math.max(200, dimensions.width - 240)])
    return { root: layoutFn(root), treeHeight }
  }, [treeDatum, dimensions])

  // Select a node from autocomplete
  const selectNode = useCallback((node: GraphNode) => {
    setSelectedNode(node)
    setQuery(node.name)
    setShowDropdown(false)
    setHighlightIdx(-1)
  }, [])

  // Keyboard navigation for autocomplete
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!showDropdown || matches.length === 0) {
        if (e.key === 'Escape') {
          setShowDropdown(false)
        }
        return
      }

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setHighlightIdx((prev) => (prev < matches.length - 1 ? prev + 1 : 0))
          break
        case 'ArrowUp':
          e.preventDefault()
          setHighlightIdx((prev) => (prev > 0 ? prev - 1 : matches.length - 1))
          break
        case 'Enter':
          e.preventDefault()
          if (highlightIdx >= 0 && highlightIdx < matches.length) {
            selectNode(matches[highlightIdx])
          }
          break
        case 'Escape':
          e.preventDefault()
          setShowDropdown(false)
          setHighlightIdx(-1)
          break
      }
    },
    [showDropdown, matches, highlightIdx, selectNode],
  )

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // Navigate to graph when clicking a tree node
  const handleTreeNodeClick = useCallback(
    (datum: TreeDatum) => {
      if (datum.nodeId.startsWith('__')) return
      setPendingSearch(datum.name)
      navigate({ to: '/graph' })
    },
    [setPendingSearch, navigate],
  )

  // D3 link generator
  const linkGen = linkHorizontal<{ source: [number, number]; target: [number, number] }, [number, number]>()
    .x((d) => d[0])
    .y((d) => d[1])

  if (!graph) {
    return (
      <div className="p-6 view-enter h-full">
        <EmptyState
          icon="oo"
          title="No graph data loaded"
          description="Load a code_graph.json file to explore dependency chains."
          actionLabel="Go to Dashboard"
          actionTo="/"
        />
      </div>
    )
  }

  return (
    <div className="p-6 view-enter flex flex-col h-full gap-4">
      <h1 className="text-2xl font-heading">Dependencies</h1>

      {/* Search with autocomplete */}
      <div className="relative max-w-md">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setShowDropdown(true)
            setHighlightIdx(-1)
          }}
          onFocus={() => {
            if (query.trim()) setShowDropdown(true)
          }}
          onKeyDown={handleKeyDown}
          placeholder="Search for a symbol to explore its dependencies..."
          aria-label="Search symbols"
          className="w-full px-3 py-2 text-sm rounded-base border-2 border-border bg-bg2 text-fg placeholder:text-fg/30 neo-focus font-base"
        />
        {showDropdown && matches.length > 0 && (
          <div
            ref={dropdownRef}
            className="absolute z-50 left-0 right-0 mt-1 rounded-base border-2 border-border shadow-neo bg-bg2 max-h-64 overflow-y-auto"
          >
            {matches.map((node, idx) => (
              <button
                type="button"
                key={node.id}
                className={`w-full text-left px-3 py-2 text-sm font-base flex items-center gap-2 cursor-pointer transition-colors ${
                  idx === highlightIdx ? 'bg-main/20 text-fg' : 'text-fg/80 hover:bg-bg/50'
                }`}
                onMouseEnter={() => setHighlightIdx(idx)}
                onClick={() => selectNode(node)}
              >
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: nodeColor(node.node_type) }} />
                <span className="truncate font-heading">{node.name}</span>
                <span className="ml-auto text-[10px] text-fg/40 truncate max-w-[160px]">
                  {shortPath(node.file_path)}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Selected node info */}
      {selectedNode && (
        <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-3 flex items-center gap-3">
          <span className="w-3 h-3 rounded-full shrink-0" style={{ background: nodeColor(selectedNode.node_type) }} />
          <div>
            <p className="font-heading text-sm">{selectedNode.name}</p>
            <p className="text-[11px] text-fg/50">
              {selectedNode.node_type} &middot; {shortPath(selectedNode.file_path)}
            </p>
          </div>
          <div className="ml-auto flex gap-2 text-[11px] text-fg/50">
            <span>{outEdges.get(selectedNode.id)?.length ?? 0} outgoing</span>
            <span>{inEdges.get(selectedNode.id)?.length ?? 0} incoming</span>
          </div>
        </div>
      )}

      {/* Tree visualization */}
      <div
        ref={containerRef}
        className="flex-1 rounded-base border-2 border-border shadow-neo bg-bg2 overflow-auto min-h-0"
      >
        {!selectedNode && (
          <div className="flex items-center justify-center h-full text-fg/30 text-sm font-base">
            Select a symbol above to see its dependency tree
          </div>
        )}
        {selectedNode && treeDatum && (!treeDatum.children || treeDatum.children.length === 0) && (
          <div className="flex items-center justify-center h-full text-fg/30 text-sm font-base">
            No dependency relationships found for this symbol
          </div>
        )}
        {selectedNode && treeLayout && (
          <svg
            ref={svgRef}
            width={dimensions.width}
            height={Math.max(dimensions.height, treeLayout.treeHeight + 40)}
            className="w-full"
            aria-hidden="true"
          >
            <g transform="translate(160, 20)">
              {/* Links */}
              {treeLayout.root.links().map((link, i) => {
                const edgeType = (link.target.data as TreeDatum).edgeType
                return (
                  <path
                    key={`link-${i}`}
                    d={
                      linkGen({
                        source: [link.source.y, link.source.x],
                        target: [link.target.y, link.target.x],
                      }) ?? ''
                    }
                    fill="none"
                    stroke={edgeType ? edgeColor(edgeType) : 'var(--border)'}
                    strokeWidth={1.5}
                    strokeOpacity={0.6}
                  />
                )
              })}

              {/* Nodes */}
              {treeLayout.root.descendants().map((d, i) => {
                const datum = d.data
                const isGroup = datum.nodeId.startsWith('__')
                const isRoot = d.depth === 0

                return (
                  // biome-ignore lint/a11y/noStaticElementInteractions: SVG <g> elements cannot be semantic buttons
                  <g
                    key={`node-${i}`}
                    transform={`translate(${d.y},${d.x})`}
                    tabIndex={isGroup ? undefined : 0}
                    style={{ cursor: isGroup ? 'default' : 'pointer' }}
                    onClick={() => {
                      if (!isGroup && !isRoot) handleTreeNodeClick(datum)
                    }}
                    onKeyDown={(e) => {
                      if ((e.key === 'Enter' || e.key === ' ') && !isGroup && !isRoot) {
                        e.preventDefault()
                        handleTreeNodeClick(datum)
                      }
                    }}
                    onMouseEnter={(e) => {
                      if (!isGroup) {
                        tooltip.show(
                          `<strong>${datum.name}</strong><br/>` +
                            `<span style="color:${nodeColor(datum.nodeType)}">${datum.nodeType}</span>` +
                            (datum.edgeType ? `<br/><span style="opacity:0.7">via ${datum.edgeType}</span>` : '') +
                            (datum.filePath
                              ? `<br/><span style="opacity:0.7">${shortPath(datum.filePath)}</span>`
                              : ''),
                          e.clientX,
                          e.clientY,
                        )
                      }
                    }}
                    onMouseMove={(e) => tooltip.move(e.clientX, e.clientY)}
                    onMouseLeave={() => tooltip.hide()}
                  >
                    {isGroup ? (
                      <>
                        <rect
                          x={-40}
                          y={-10}
                          width={80}
                          height={20}
                          rx={4}
                          fill="var(--secondary-background)"
                          stroke="var(--border)"
                          strokeWidth={1.5}
                        />
                        <text
                          textAnchor="middle"
                          dy="4"
                          className="fill-fg/60"
                          style={{ fontSize: 10, fontWeight: 600 }}
                        >
                          {datum.name}
                        </text>
                      </>
                    ) : (
                      <>
                        <circle
                          r={isRoot ? 8 : 5}
                          fill={nodeColor(datum.nodeType)}
                          stroke="var(--border)"
                          strokeWidth={1.5}
                          fillOpacity={0.8}
                        />
                        <text x={isRoot ? 12 : 10} dy="3.5" className="fill-fg" style={{ fontSize: isRoot ? 12 : 10 }}>
                          {datum.name.length > 28 ? `${datum.name.slice(0, 26)}...` : datum.name}
                        </text>
                        {datum.edgeType && (
                          <text x={10} dy={-6} style={{ fontSize: 8 }} fill={edgeColor(datum.edgeType)} opacity={0.7}>
                            {datum.edgeType}
                          </text>
                        )}
                      </>
                    )}
                  </g>
                )
              })}
            </g>
          </svg>
        )}
      </div>
    </div>
  )
}
