import { createFileRoute, Link } from '@tanstack/react-router'
import { useMemo } from 'react'
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { EmptyState } from '../components/empty-state'
import { StatCard } from '../components/stat-card'
import { NODE_COLORS, nodeColor } from '../constants/colors'
import { computeDegreeCentrality, findEntryPoints, shortPath } from '../lib/graph-utils'
import { useStore } from '../store/use-store'
import type { GraphNode } from '../types'

export const Route = createFileRoute('/hotspots')({
  component: HotspotsView,
})

type RankedNode = GraphNode & { inDegree: number; outDegree: number; totalDegree: number }

function HotspotsView() {
  const graph = useStore((s) => s.graph)
  const setPendingSearch = useStore((s) => s.setPendingSearch)

  const { ranked, hotspots, entryPoints, avgDegree, top20, epData, topFiles, histogramData } = useMemo(() => {
    if (!graph || graph.nodes.length === 0) {
      return {
        ranked: [],
        hotspots: [],
        entryPoints: [],
        avgDegree: '0',
        top20: [],
        epData: [],
        topFiles: [],
        histogramData: [],
      }
    }

    const ranked = computeDegreeCentrality(graph) as RankedNode[]
    const totalNodes = ranked.length
    const threshold = Math.max(1, Math.ceil(totalNodes * 0.05))
    const hotspots = ranked.slice(0, threshold)
    const entryPoints = findEntryPoints(graph) as RankedNode[]
    const avgDegree = totalNodes > 0 ? (ranked.reduce((s, n) => s + n.totalDegree, 0) / totalNodes).toFixed(1) : '0'

    const top20 = ranked.slice(0, 20).map((n) => ({
      label: `${shortPath(n.file_path)}:${n.name}`,
      value: n.totalDegree,
      color: nodeColor(n.node_type),
    }))

    const epData = entryPoints.map((n) => ({
      label: `${shortPath(n.file_path)}:${n.name}`,
      value: n.outDegree,
      color: nodeColor(n.node_type),
    }))

    // Top files
    const fileMap = new Map<string, { symbols: RankedNode[]; totalDegree: number }>()
    for (const n of ranked) {
      const fp = n.file_path || '(unknown)'
      if (!fileMap.has(fp)) fileMap.set(fp, { symbols: [], totalDegree: 0 })
      const entry = fileMap.get(fp)!
      entry.symbols.push(n)
      entry.totalDegree += n.totalDegree
    }
    const topFiles = Array.from(fileMap.entries())
      .map(([fp, data]) => ({
        filePath: fp,
        symbolCount: data.symbols.length,
        avgDegree: (data.totalDegree / data.symbols.length).toFixed(1),
        topSymbol: data.symbols.sort((a, b) => b.totalDegree - a.totalDegree)[0]?.name ?? '',
      }))
      .sort((a, b) => b.symbolCount - a.symbolCount)
      .slice(0, 30)

    // Histogram data
    const degrees = ranked.map((n) => n.totalDegree)
    const maxDeg = Math.max(...degrees, 1)
    const binCount = 20
    const binSize = Math.max(1, Math.ceil(maxDeg / binCount))
    const bins: Array<{ range: string; count: number }> = []
    for (let i = 0; i < binCount; i++) {
      const lo = i * binSize
      const hi = lo + binSize
      const count = degrees.filter((d) => d >= lo && d < hi).length
      if (count > 0 || i < 10) bins.push({ range: `${lo}–${hi}`, count })
    }

    return { ranked, hotspots, entryPoints, avgDegree, top20, epData, topFiles, histogramData: bins }
  }, [graph])

  if (!graph || graph.nodes.length === 0) {
    return (
      <EmptyState
        title="No Graph Data"
        description="Load a code_graph.json file to see centrality analysis."
        actionLabel="Go to Dashboard"
        actionTo="/"
      />
    )
  }

  return (
    <div className="p-6 space-y-6 view-enter">
      <div>
        <h1 className="text-2xl font-heading">Centrality Hotspots</h1>
        <p className="text-sm text-fg/60 font-base mt-1">
          Nodes with the highest degree centrality — the most connected symbols in your codebase.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard title="Total Nodes" value={ranked.length.toLocaleString()} />
        <StatCard title="Hotspots (Top 5%)" value={hotspots.length.toLocaleString()} color={NODE_COLORS.function} />
        <StatCard title="Entry Points" value={entryPoints.length.toLocaleString()} color={NODE_COLORS.class} />
        <StatCard title="Avg Degree" value={avgDegree} />
      </div>

      {/* Bar Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
          <h2 className="font-heading text-sm mb-3">Top 20 Hotspots</h2>
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={top20} layout="vertical" margin={{ left: 0, right: 16 }}>
              <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--foreground)' }} />
              <YAxis
                type="category"
                dataKey="label"
                width={160}
                tick={{ fontSize: 10, fill: 'var(--foreground)' }}
                tickFormatter={(v: string) => (v.length > 25 ? `${v.slice(0, 23)}…` : v)}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--secondary-background)',
                  border: '2px solid var(--border)',
                  borderRadius: '5px',
                  fontSize: '12px',
                }}
              />
              <Bar dataKey="value" stroke="var(--border)" strokeWidth={2} radius={[0, 3, 3, 0]}>
                {top20.map((item, i) => (
                  <Cell key={i} fill={item.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
          <h2 className="font-heading text-sm mb-3">Entry Points</h2>
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={epData} layout="vertical" margin={{ left: 0, right: 16 }}>
              <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--foreground)' }} />
              <YAxis
                type="category"
                dataKey="label"
                width={160}
                tick={{ fontSize: 10, fill: 'var(--foreground)' }}
                tickFormatter={(v: string) => (v.length > 25 ? `${v.slice(0, 23)}…` : v)}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--secondary-background)',
                  border: '2px solid var(--border)',
                  borderRadius: '5px',
                  fontSize: '12px',
                }}
              />
              <Bar dataKey="value" stroke="var(--border)" strokeWidth={2} radius={[0, 3, 3, 0]}>
                {epData.map((item, i) => (
                  <Cell key={i} fill={item.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Degree Distribution Histogram */}
      <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
        <h2 className="font-heading text-sm mb-3">Degree Distribution</h2>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={histogramData} margin={{ left: 8, right: 16, bottom: 20 }}>
            <XAxis
              dataKey="range"
              tick={{ fontSize: 10, fill: 'var(--foreground)' }}
              label={{ value: 'Degree', position: 'bottom', offset: 0, fontSize: 11, fill: 'var(--foreground)' }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--foreground)' }}
              label={{ value: 'Count', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--foreground)' }}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--secondary-background)',
                border: '2px solid var(--border)',
                borderRadius: '5px',
                fontSize: '12px',
              }}
            />
            <Bar dataKey="count" fill="var(--chart-1)" stroke="var(--border)" strokeWidth={2} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Top Files Table */}
      <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
        <h2 className="font-heading text-sm mb-3">Top Files</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-base table-fixed">
            <thead>
              <tr className="border-b-2 border-border text-left">
                <th className="py-2 px-3 font-heading w-1/2">File Path</th>
                <th className="py-2 px-3 font-heading text-right w-20">Symbols</th>
                <th className="py-2 px-3 font-heading text-right w-24">Avg Degree</th>
                <th className="py-2 px-3 font-heading w-1/4">Top Symbol</th>
              </tr>
            </thead>
            <tbody>
              {topFiles.map((f) => (
                <tr key={f.filePath} className="border-b border-border/30 hover:bg-main/5">
                  <td className="py-1.5 px-3 break-anywhere" title={f.filePath}>
                    <Link
                      to="/graph"
                      onClick={() => setPendingSearch(shortPath(f.filePath))}
                      className="hover:text-main hover:underline cursor-pointer"
                      title="View in Graph Explorer"
                    >
                      {shortPath(f.filePath)}
                    </Link>
                  </td>
                  <td className="py-1.5 px-3 text-right font-heading">{f.symbolCount}</td>
                  <td className="py-1.5 px-3 text-right">{f.avgDegree}</td>
                  <td className="py-1.5 text-fg/70 px-3 break-anywhere">
                    <Link
                      to="/graph"
                      onClick={() => setPendingSearch(f.topSymbol)}
                      className="hover:text-main hover:underline cursor-pointer"
                    >
                      {f.topSymbol}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
