import { createFileRoute } from '@tanstack/react-router'
import type { D3DragEvent } from 'd3-drag'
import { drag } from 'd3-drag'
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force'
import { select } from 'd3-selection'
import type { D3ZoomEvent, ZoomTransform } from 'd3-zoom'
import { zoom, zoomIdentity } from 'd3-zoom'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ColorLegend } from '../components/color-legend'
import { EmptyState } from '../components/empty-state'
import { FilterChips } from '../components/filter-chips'
import { SearchBar } from '../components/search-bar'
import { EDGE_COLORS, EDGE_TYPE_LABELS, edgeColor, NODE_COLORS, NODE_TYPE_LABELS, nodeColor } from '../constants/colors'
import { detectModules, filterGraph, shortPath } from '../lib/graph-utils'
import { useStore } from '../store/use-store'
// GraphNode/GraphEdge types used via graph store

export const Route = createFileRoute('/graph')({
  component: GraphView,
})

/* ---------- D3 node / link types ---------- */

interface SimNode extends SimulationNodeDatum {
  id: string
  name: string
  node_type: string
  file_path: string
  line_start: number
  line_end: number
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  source: string | SimNode
  target: string | SimNode
  edge_type: string
  weight: number
  confidence?: number
}

type NodeDragEvent = D3DragEvent<SVGGElement, SimNode, SimNode>
type SvgZoomEvent = D3ZoomEvent<SVGSVGElement, unknown>

/* ---------- Component ---------- */

function GraphView() {
  const graph = useStore((s) => s.graph)
  const pendingSearch = useStore((s) => s.pendingSearch)
  const setPendingSearch = useStore((s) => s.setPendingSearch)

  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const minimapRef = useRef<SVGSVGElement>(null)
  const simulationRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null)

  const [searchQuery, setSearchQuery] = useState('')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [activeNodeTypes, setActiveNodeTypes] = useState<Set<string>>(new Set())
  const [activeEdgeTypes, setActiveEdgeTypes] = useState<Set<string>>(new Set())
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const currentTransformRef = useRef<ZoomTransform>(zoomIdentity)

  // Initialize filter sets
  useEffect(() => {
    if (!graph) return
    setActiveNodeTypes(new Set(graph.nodes.map((n) => n.node_type)))
    setActiveEdgeTypes(new Set(graph.links.map((e) => e.edge_type)))
  }, [graph])

  // Consume pending search
  useEffect(() => {
    if (pendingSearch) {
      setSearchQuery(pendingSearch)
      setPendingSearch(null)
    }
  }, [pendingSearch, setPendingSearch])

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

  // Filter graph
  const filtered = useMemo(() => {
    if (!graph) return { nodes: [], links: [] }
    return filterGraph(graph, activeNodeTypes, activeEdgeTypes)
  }, [graph, activeNodeTypes, activeEdgeTypes])

  // Apply search filter
  const searchFiltered = useMemo(() => {
    if (!searchQuery) return filtered
    const q = searchQuery.toLowerCase()
    const matchNodes = filtered.nodes.filter(
      (n) => n.name.toLowerCase().includes(q) || n.file_path.toLowerCase().includes(q),
    )
    const nodeIds = new Set(matchNodes.map((n) => n.id))
    for (const edge of filtered.links) {
      if (nodeIds.has(edge.source)) nodeIds.add(edge.target)
      if (nodeIds.has(edge.target)) nodeIds.add(edge.source)
    }
    const nodes = filtered.nodes.filter((n) => nodeIds.has(n.id))
    const links = filtered.links.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
    return { nodes, links }
  }, [filtered, searchQuery])

  // Selected node details
  const selectedNode = useMemo(() => {
    if (!selectedNodeId || !graph) return null
    return graph.nodes.find((n) => n.id === selectedNodeId) ?? null
  }, [selectedNodeId, graph])

  const selectedEdges = useMemo(() => {
    if (!selectedNodeId || !graph) return []
    return graph.links.filter((e) => e.source === selectedNodeId || e.target === selectedNodeId)
  }, [selectedNodeId, graph])

  /* ---- Main D3 rendering effect ---- */
  useEffect(() => {
    const svgEl = svgRef.current
    if (!svgEl) return

    const { nodes: gNodes, links: gLinks } = searchFiltered
    if (gNodes.length === 0) {
      select(svgEl).selectAll('*').remove()
      return
    }

    const svg = select(svgEl)
    svg.selectAll('*').remove()

    const { width, height } = dimensions

    // Module clustering
    const modules = detectModules({ nodes: gNodes, links: gLinks })
    const moduleIndex = new Map<string, number>()
    modules.forEach((mod, i) => {
      for (const member of mod.members) moduleIndex.set(member.id, i)
    })
    const moduleCount = Math.max(1, modules.length)
    const clusterRadius = Math.min(width, height) * 0.35
    const moduleTargets = modules.map((_, i) => ({
      x: width / 2 + clusterRadius * Math.cos((2 * Math.PI * i) / moduleCount),
      y: height / 2 + clusterRadius * Math.sin((2 * Math.PI * i) / moduleCount),
    }))

    // Build simulation data (deep copy)
    const simNodes: SimNode[] = gNodes.map((n) => ({
      ...n,
      x: width / 2 + (Math.random() - 0.5) * 200,
      y: height / 2 + (Math.random() - 0.5) * 200,
    }))
    const simLinks: SimLink[] = gLinks.map((e) => ({ ...e }))

    // Create simulation
    const simulation = forceSimulation(simNodes)
      .force(
        'link',
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance(60),
      )
      .force('charge', forceManyBody().strength(-150))
      .force('center', forceCenter(width / 2, height / 2))
      .force('collide', forceCollide().radius(20))
      .force(
        'moduleX',
        forceX<SimNode>((d) => {
          const idx = moduleIndex.get(d.id)
          return idx !== undefined ? moduleTargets[idx].x : width / 2
        }).strength(0.08),
      )
      .force(
        'moduleY',
        forceY<SimNode>((d) => {
          const idx = moduleIndex.get(d.id)
          return idx !== undefined ? moduleTargets[idx].y : height / 2
        }).strength(0.08),
      )

    simulationRef.current = simulation

    // Inner group for zoom transform
    const g = svg.append('g')

    // Arrow marker defs
    const defs = svg.append('defs')
    const edgeTypesInData = new Set(gLinks.map((e) => e.edge_type))
    for (const et of edgeTypesInData) {
      defs
        .append('marker')
        .attr('id', `arrow-${et}`)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 18)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', edgeColor(et))
    }

    // Render links
    const linkGroup = g.append('g').attr('class', 'links')
    const link = linkGroup
      .selectAll('line')
      .data(simLinks)
      .join('line')
      .attr('stroke', (d) => edgeColor(d.edge_type))
      .attr('stroke-width', (d) => Math.min(3, d.weight))
      .attr('stroke-opacity', 0.5)
      .attr('marker-end', (d) => `url(#arrow-${d.edge_type})`)
      .on('mouseenter', (event: MouseEvent, d: SimLink) => {
        const src = d.source as SimNode
        const tgt = d.target as SimNode
        showTooltipAtPos(
          event.clientX,
          event.clientY,
          `<div class="text-xs">
            <span class="font-heading">${escapeHtml(EDGE_TYPE_LABELS[d.edge_type] ?? d.edge_type)}</span><br/>
            ${escapeHtml(src.name)} → ${escapeHtml(tgt.name)}<br/>
            Weight: ${d.weight}${d.confidence != null ? `<br/>Confidence: ${d.confidence.toFixed(2)}` : ''}
          </div>`,
        )
      })
      .on('mouseleave', hideTooltipEl)

    // Render nodes
    const nodeGroup = g.append('g').attr('class', 'nodes')
    const node = nodeGroup
      .selectAll<SVGGElement, SimNode>('g')
      .data(simNodes)
      .join('g')
      .attr('class', 'graph-node')
      .style('cursor', 'pointer')

    // Node background rect
    node
      .append('rect')
      .attr('rx', 5)
      .attr('ry', 5)
      .attr('x', -30)
      .attr('y', -10)
      .attr('width', 60)
      .attr('height', 20)
      .attr('fill', (d) => nodeColor(d.node_type))
      .attr('stroke', 'var(--border)')
      .attr('stroke-width', 2)
      .attr('opacity', (d) => {
        if (!searchQuery) return 1
        return d.name.toLowerCase().includes(searchQuery.toLowerCase()) ? 1 : 0.25
      })

    // Node label
    node
      .append('text')
      .text((d) => (d.name.length > 12 ? `${d.name.slice(0, 10)}...` : d.name))
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('font-size', '10px')
      .attr('font-weight', 600)
      .attr('font-family', "'DM Sans', sans-serif")
      .attr('fill', '#000')
      .attr('pointer-events', 'none')

    // Node interaction
    node
      .on('click', (_event: MouseEvent, d: SimNode) => {
        setSelectedNodeId(d.id)
      })
      .on('mouseenter', (event: MouseEvent, d: SimNode) => {
        showTooltipAtPos(
          event.clientX,
          event.clientY,
          `<div class="text-xs">
            <span class="font-heading">${escapeHtml(d.name)}</span><br/>
            <span class="text-fg/60">${escapeHtml(NODE_TYPE_LABELS[d.node_type] ?? d.node_type)}</span><br/>
            <span class="text-fg/40">${escapeHtml(shortPath(d.file_path))}</span>
          </div>`,
        )
      })
      .on('mouseleave', hideTooltipEl)

    // Drag behavior
    const dragBehavior = drag<SVGGElement, SimNode, SimNode>()
      .on('start', (event: NodeDragEvent) => {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        event.subject.fx = event.subject.x
        event.subject.fy = event.subject.y
      })
      .on('drag', (event: NodeDragEvent) => {
        event.subject.fx = event.x
        event.subject.fy = event.y
      })
      .on('end', (event: NodeDragEvent) => {
        if (!event.active) simulation.alphaTarget(0)
        event.subject.fx = null
        event.subject.fy = null
      })
    node.call(dragBehavior)

    // Zoom behavior
    const zoomBehavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.05, 6])
      .on('zoom', (event: SvgZoomEvent) => {
        g.attr('transform', event.transform.toString())
        currentTransformRef.current = event.transform
        updateMinimap(simNodes, event.transform)
      })
    svg.call(zoomBehavior)

    // Click on background to deselect
    svg.on('click', (event: MouseEvent) => {
      if (event.target === svgEl) setSelectedNodeId(null)
    })

    // Tick handler
    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as SimNode).x!)
        .attr('y1', (d) => (d.source as SimNode).y!)
        .attr('x2', (d) => (d.target as SimNode).x!)
        .attr('y2', (d) => (d.target as SimNode).y!)

      node.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

    // Minimap rendering
    function updateMinimap(nodes: SimNode[], t: ZoomTransform) {
      const mm = minimapRef.current
      if (!mm) return
      const mmSvg = select(mm)
      mmSvg.selectAll('*').remove()

      const mmW = 150
      const mmH = 100

      let minX = Infinity,
        minY = Infinity,
        maxX = -Infinity,
        maxY = -Infinity
      for (const n of nodes) {
        if (n.x! < minX) minX = n.x!
        if (n.y! < minY) minY = n.y!
        if (n.x! > maxX) maxX = n.x!
        if (n.y! > maxY) maxY = n.y!
      }
      const rangeX = maxX - minX || 1
      const rangeY = maxY - minY || 1
      const pad = 10
      const scaleX = (mmW - pad * 2) / rangeX
      const scaleY = (mmH - pad * 2) / rangeY
      const s = Math.min(scaleX, scaleY)

      for (const n of nodes) {
        mmSvg
          .append('circle')
          .attr('cx', pad + (n.x! - minX) * s)
          .attr('cy', pad + (n.y! - minY) * s)
          .attr('r', 1.5)
          .attr('fill', nodeColor(n.node_type))
          .attr('opacity', 0.7)
      }

      const vx = (-t.x / t.k - minX) * s + pad
      const vy = (-t.y / t.k - minY) * s + pad
      const vw = (width / t.k) * s
      const vh = (height / t.k) * s
      mmSvg
        .append('rect')
        .attr('x', vx)
        .attr('y', vy)
        .attr('width', vw)
        .attr('height', vh)
        .attr('fill', 'none')
        .attr('stroke', 'var(--main)')
        .attr('stroke-width', 1.5)
        .attr('opacity', 0.7)
    }

    // Initial minimap after simulation settles
    simulation.on('end.minimap', () => {
      updateMinimap(simNodes, currentTransformRef.current)
    })

    // Fit to view after initial layout
    const fitTimer = setTimeout(() => {
      let minX = Infinity,
        minY = Infinity,
        maxX = -Infinity,
        maxY = -Infinity
      for (const n of simNodes) {
        if (n.x! < minX) minX = n.x!
        if (n.y! < minY) minY = n.y!
        if (n.x! > maxX) maxX = n.x!
        if (n.y! > maxY) maxY = n.y!
      }
      const rangeX = maxX - minX || 1
      const rangeY = maxY - minY || 1
      const padding = 80
      const scale = Math.min((width - padding * 2) / rangeX, (height - padding * 2) / rangeY, 1.5)
      const cx = (minX + maxX) / 2
      const cy = (minY + maxY) / 2
      const tx = width / 2 - cx * scale
      const ty = height / 2 - cy * scale

      svg.transition().duration(800).call(zoomBehavior.transform, zoomIdentity.translate(tx, ty).scale(scale))
    }, 2000)

    return () => {
      clearTimeout(fitTimer)
      simulation.stop()
      svg.selectAll('*').remove()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchFiltered, dimensions, searchQuery])

  // Toggle filters
  const toggleNodeType = useCallback((type: string) => {
    setActiveNodeTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }, [])

  const toggleEdgeType = useCallback((type: string) => {
    setActiveEdgeTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }, [])

  if (!graph) {
    return (
      <EmptyState
        icon="🔗"
        title="No Graph Data"
        description="Load a code_graph.json file to explore the codebase graph."
        actionLabel="Go to Home"
        actionTo="/"
      />
    )
  }

  const nodeChips = Object.entries(NODE_COLORS).map(([type, color]) => ({
    type,
    label: NODE_TYPE_LABELS[type] ?? type,
    color,
    active: activeNodeTypes.has(type),
  }))
  const edgeChips = Object.entries(EDGE_COLORS).map(([type, color]) => ({
    type,
    label: EDGE_TYPE_LABELS[type] ?? type,
    color,
    active: activeEdgeTypes.has(type),
  }))

  return (
    <div className="h-full flex flex-col view-enter">
      {/* Toolbar */}
      <div className="p-3 border-b-2 border-border bg-bg2 space-y-2">
        <div className="flex items-center gap-3">
          <SearchBar placeholder="Search nodes..." onSearch={setSearchQuery} initialValue={searchQuery} />
          <ColorLegend />
          <span className="text-xs text-fg/40 font-base ml-auto">
            {searchFiltered.nodes.length} nodes · {searchFiltered.links.length} edges
          </span>
        </div>
        <div className="flex gap-4">
          <FilterChips chips={nodeChips} onToggle={toggleNodeType} title="Nodes" />
          <FilterChips chips={edgeChips} onToggle={toggleEdgeType} title="Edges" />
        </div>
        <p className="text-[10px] text-fg/30">
          Drag nodes to rearrange · scroll to zoom · click background to deselect
        </p>
      </div>

      {/* Graph canvas */}
      <div ref={containerRef} className="flex-1 relative overflow-hidden bg-bg">
        <svg
          ref={svgRef}
          width={dimensions.width}
          height={dimensions.height}
          className="w-full h-full"
          style={{ cursor: 'grab' }}
          aria-hidden="true"
        />

        {/* Minimap */}
        <div className="absolute bottom-3 right-3 rounded-base border-2 border-border bg-bg2/90 shadow-neo overflow-hidden">
          <svg ref={minimapRef} width={150} height={100} aria-hidden="true" />
        </div>

        {/* Detail panel */}
        {selectedNode && (
          <div className="absolute top-3 right-3 w-72 rounded-base border-2 border-border shadow-neo bg-bg2 p-3 max-h-[70vh] overflow-auto">
            <div className="flex items-start justify-between mb-2">
              <h3 className="font-heading text-sm truncate-line flex-1">{selectedNode.name}</h3>
              <button
                type="button"
                onClick={() => setSelectedNodeId(null)}
                className="text-fg/40 hover:text-fg cursor-pointer ml-2 p-1"
              >
                ✕
              </button>
            </div>
            <div className="space-y-1 text-xs">
              <p>
                <span className="text-fg/50">Type:</span>{' '}
                <span className="font-heading" style={{ color: nodeColor(selectedNode.node_type) }}>
                  {NODE_TYPE_LABELS[selectedNode.node_type] ?? selectedNode.node_type}
                </span>
              </p>
              <p className="truncate-line">
                <span className="text-fg/50">File:</span> {shortPath(selectedNode.file_path)}
              </p>
              <p>
                <span className="text-fg/50">Lines:</span> {selectedNode.line_start}–{selectedNode.line_end}
              </p>
              <p>
                <span className="text-fg/50">Connections:</span> {selectedEdges.length}
              </p>
            </div>
            {selectedEdges.length > 0 && (
              <div className="mt-3">
                <p className="text-[10px] font-heading uppercase tracking-wide text-fg/40 mb-1">Connections</p>
                <ul className="space-y-0.5 max-h-48 overflow-auto">
                  {selectedEdges.map((e, i) => {
                    const neighborId = e.source === selectedNodeId ? e.target : e.source
                    const neighbor = graph.nodes.find((n) => n.id === neighborId)
                    return (
                      <li key={i} className="flex items-center gap-1.5 text-xs text-fg/70">
                        <span
                          className="text-[10px] px-1 rounded border border-border/30"
                          style={{ color: edgeColor(e.edge_type) }}
                        >
                          {e.edge_type}
                        </span>
                        <button
                          type="button"
                          onClick={() => setSelectedNodeId(neighborId)}
                          className="text-left hover:text-main hover:underline cursor-pointer truncate-line flex-1"
                        >
                          {neighbor?.name ?? neighborId}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* ---------- Tooltip helpers (imperative DOM for perf) ---------- */

let tooltipEl: HTMLDivElement | null = null

function getTooltipEl(): HTMLDivElement {
  if (!tooltipEl) {
    tooltipEl = document.createElement('div')
    tooltipEl.className =
      'fixed z-[9999] pointer-events-none px-2 py-1 rounded-base border-2 border-border bg-bg2 shadow-neo text-fg'
    tooltipEl.style.display = 'none'
    document.body.appendChild(tooltipEl)
  }
  return tooltipEl
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function showTooltipAtPos(x: number, y: number, html: string) {
  const el = getTooltipEl()
  el.innerHTML = html
  el.style.display = 'block'
  el.style.left = `${x + 12}px`
  el.style.top = `${y - 8}px`
}

function hideTooltipEl() {
  const el = getTooltipEl()
  el.style.display = 'none'
}
