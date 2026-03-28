import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { hierarchy, pack } from 'd3-hierarchy'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { EmptyState } from '../components/empty-state'
import { StatCard } from '../components/stat-card'
import { useTooltip } from '../components/tooltip'
import { NODE_COLORS, NODE_TYPE_LABELS, nodeColor } from '../constants/colors'
import { buildHierarchy, shortPath } from '../lib/graph-utils'
import { useStore } from '../store/use-store'
import type { GraphNode } from '../types'

export const Route = createFileRoute('/modules')({
  component: ModulesView,
})

interface HierarchyLeaf {
  name: string
  value: number
  node: GraphNode
}

interface HierarchyBranch {
  name: string
  children: (HierarchyLeaf | HierarchyBranch)[]
}

type HierarchyDatum = HierarchyLeaf | HierarchyBranch

/** Return SVG polygon points for a flat-top regular hexagon centered at (cx, cy) with circumradius r. */
function hexagonPoints(cx: number, cy: number, r: number): string {
  return Array.from({ length: 6 }, (_, i) => {
    const angle = (Math.PI / 3) * i - Math.PI / 6 // flat-top hexagon
    return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`
  }).join(' ')
}

function ModulesView() {
  const graph = useStore((s) => s.graph)
  const setPendingSearch = useStore((s) => s.setPendingSearch)
  const navigate = useNavigate()
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const tooltip = useTooltip()

  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [zoomedNode, setZoomedNode] = useState<string | null>(null)

  // Observe container size
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) {
        setDimensions({ width, height })
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // Build hierarchy data
  const hierData = useMemo(() => {
    if (!graph) return null
    return buildHierarchy(graph.nodes)
  }, [graph])

  // Compute packed layout
  const packed = useMemo(() => {
    if (!hierData) return null
    const root = hierarchy<HierarchyDatum>(hierData as HierarchyDatum)
      .sum((d) => ('value' in d ? (d as HierarchyLeaf).value : 0))
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))

    const packer = pack<HierarchyDatum>().size([dimensions.width, dimensions.height]).padding(3)

    return packer(root)
  }, [hierData, dimensions])

  // KPIs
  const stats = useMemo(() => {
    if (!graph) return { modules: 0, symbols: 0, avgPerModule: 0 }
    const modules = new Set(
      graph.nodes.map((n) => {
        const parts = (n.file_path || '').replace(/\\/g, '/').split('/')
        return parts.slice(0, -1).join('/') || '(root)'
      }),
    )
    return {
      modules: modules.size,
      symbols: graph.nodes.length,
      avgPerModule: modules.size > 0 ? Math.round(graph.nodes.length / modules.size) : 0,
    }
  }, [graph])

  // Handle leaf click -> navigate to graph with search
  const handleLeafClick = useCallback(
    (node: GraphNode) => {
      setPendingSearch(node.name)
      navigate({ to: '/graph' })
    },
    [setPendingSearch, navigate],
  )

  // Handle branch click -> zoom
  const handleBranchClick = useCallback((name: string) => {
    setZoomedNode((prev) => (prev === name ? null : name))
  }, [])

  if (!graph) {
    return (
      <div className="p-6 view-enter h-full">
        <EmptyState
          icon="oo"
          title="No graph data loaded"
          description="Load a code_graph.json file to see the module circle-packing visualization."
          actionLabel="Go to Dashboard"
          actionTo="/"
        />
      </div>
    )
  }

  // Determine visible nodes for zoomed state
  const visibleNodes = packed
    ? packed.descendants().filter((d) => {
        if (!zoomedNode) return true
        // Show the zoomed branch and its descendants
        if (d.data.name === zoomedNode) return true
        let ancestor = d.parent
        while (ancestor) {
          if (ancestor.data.name === zoomedNode) return true
          ancestor = ancestor.parent
        }
        return false
      })
    : []

  // Compute zoom transform
  let zoomTransform = ''
  if (zoomedNode && packed) {
    const zoomTarget = packed.descendants().find((d) => d.data.name === zoomedNode)
    if (zoomTarget) {
      const r = zoomTarget.r
      const scale = Math.min(dimensions.width, dimensions.height) / (r * 2.2)
      const tx = dimensions.width / 2 - zoomTarget.x * scale
      const ty = dimensions.height / 2 - zoomTarget.y * scale
      zoomTransform = `translate(${tx},${ty}) scale(${scale})`
    }
  }

  return (
    <div className="p-6 view-enter flex flex-col h-full gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-heading">Modules</h1>
        {zoomedNode && (
          <button
            type="button"
            onClick={() => setZoomedNode(null)}
            className="text-xs px-3 py-1 rounded-base border-2 border-border bg-bg2 shadow-neo neo-pressable font-base cursor-pointer"
          >
            Reset Zoom
          </button>
        )}
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard title="Total Modules" value={stats.modules} color="#f472b6" />
        <StatCard title="Total Symbols" value={stats.symbols} color="#60a5fa" />
        <StatCard title="Avg Symbols / Module" value={stats.avgPerModule} color="#34d399" />
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5 text-xs text-fg/60">
            <svg width="12" height="12" viewBox="0 0 12 12" className="shrink-0" aria-hidden="true">
              <polygon
                points={hexagonPoints(6, 6, 5.5)}
                fill={color}
                stroke={color}
                strokeWidth={0.5}
                strokeOpacity={0.5}
              />
            </svg>
            {NODE_TYPE_LABELS[type] ?? type}
          </div>
        ))}
      </div>

      {/* Circle packing SVG */}
      <div
        ref={containerRef}
        className="flex-1 rounded-base border-2 border-border shadow-neo bg-bg2 overflow-hidden min-h-0"
      >
        {packed && (
          <svg
            ref={svgRef}
            width={dimensions.width}
            height={dimensions.height}
            className="w-full h-full"
            aria-hidden="true"
          >
            <g style={{ transition: 'transform 0.5s ease', transform: zoomTransform }}>
              {(zoomedNode ? visibleNodes : packed.descendants()).map((d, i) => {
                const isLeaf = !d.children
                const isGroup = !!d.children && d.depth > 0
                const datum = d.data as HierarchyDatum
                const leafNode = isLeaf && 'node' in datum ? (datum as HierarchyLeaf).node : null

                // Shared event handlers for both shapes
                const sharedHandlers = {
                  onClick: () => {
                    if (isLeaf && leafNode) {
                      handleLeafClick(leafNode)
                    } else if (isGroup) {
                      handleBranchClick(datum.name)
                    }
                  },
                  onMouseEnter: (e: React.MouseEvent) => {
                    if (isLeaf && leafNode) {
                      tooltip.show(
                        `<strong>${leafNode.name}</strong><br/>` +
                          `<span style="color:${nodeColor(leafNode.node_type)}">${leafNode.node_type}</span><br/>` +
                          `<span style="opacity:0.7">${shortPath(leafNode.file_path)}</span>`,
                        e.clientX,
                        e.clientY,
                      )
                    } else if (isGroup) {
                      const count = d.leaves().length
                      tooltip.show(
                        `<strong>${shortPath(datum.name)}</strong><br/>` +
                          `<span style="opacity:0.7">${count} symbol${count !== 1 ? 's' : ''}</span>`,
                        e.clientX,
                        e.clientY,
                      )
                    }
                  },
                  onMouseMove: (e: React.MouseEvent) => tooltip.move(e.clientX, e.clientY),
                  onMouseLeave: () => tooltip.hide(),
                }

                // Leaf nodes render as hexagons; group/root nodes render as circles
                if (isLeaf) {
                  return (
                    <polygon
                      key={`${d.data.name}-${i}`}
                      points={hexagonPoints(d.x, d.y, d.r)}
                      fill={leafNode ? nodeColor(leafNode.node_type) : 'var(--secondary-background)'}
                      fillOpacity={0.75}
                      stroke={leafNode ? nodeColor(leafNode.node_type) : 'var(--border)'}
                      strokeWidth={1}
                      strokeOpacity={0.5}
                      style={{ cursor: 'pointer', transition: 'all 0.3s ease' }}
                      {...sharedHandlers}
                    />
                  )
                }

                return (
                  <circle
                    key={`${d.data.name}-${i}`}
                    cx={d.x}
                    cy={d.y}
                    r={d.r}
                    fill={d.depth === 0 ? 'transparent' : 'var(--secondary-background)'}
                    fillOpacity={0.15}
                    stroke="var(--border)"
                    strokeWidth={1.5}
                    strokeOpacity={0.3}
                    style={{ cursor: isGroup ? 'pointer' : 'default', transition: 'r 0.3s ease' }}
                    {...sharedHandlers}
                  />
                )
              })}
              {/* Labels for groups when not too zoomed out */}
              {(zoomedNode ? visibleNodes : packed.descendants())
                .filter((d) => d.depth === 1 && d.r > 30)
                .map((d, i) => {
                  const shortLabel = shortPath(d.data.name)
                  return (
                    <text
                      key={`label-${i}`}
                      x={d.x}
                      y={d.y - d.r + 14}
                      textAnchor="middle"
                      className="fill-fg/40 pointer-events-none"
                      style={{ fontSize: Math.max(9, Math.min(12, d.r / 5)) }}
                    >
                      {shortLabel.length > 20 ? `${shortLabel.slice(0, 18)}...` : shortLabel}
                    </text>
                  )
                })}
            </g>
          </svg>
        )}
      </div>
    </div>
  )
}
