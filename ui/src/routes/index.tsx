import { createFileRoute, Link } from '@tanstack/react-router'
import { useCallback, useMemo, useRef, useState } from 'react'
import { Gauge } from '../components/gauge'
import { NeoBarChart } from '../components/neo-bar-chart'
import { SeverityBadge } from '../components/severity-badge'
import { StatCard } from '../components/stat-card'
import { EDGE_COLORS, NODE_COLORS } from '../constants/colors'
import { loadFromFiles, loadFromServer } from '../lib/data-loader'
import { shortPath } from '../lib/graph-utils'
import { useStore } from '../store/use-store'
import type { ArchitecturalRisk } from '../types'

export const Route = createFileRoute('/')({
  component: IndexView,
})

function fmt(n: number | undefined | null): string {
  return (n ?? 0).toLocaleString()
}

function CategoryBadge({ category }: { category: string }) {
  let hash = 0
  for (let i = 0; i < (category || '').length; i++) {
    hash = (category || '').charCodeAt(i) + ((hash << 5) - hash)
  }
  const hue = Math.abs(hash) % 360
  const isDark = document.documentElement.classList.contains('dark')
  const bg = isDark ? `hsl(${hue}, 40%, 20%)` : `hsl(${hue}, 60%, 90%)`
  const fg = isDark ? `hsl(${hue}, 60%, 75%)` : `hsl(${hue}, 60%, 30%)`

  return (
    <span
      className="inline-flex items-center text-xs font-heading px-2 py-0.5 rounded-base border border-border/40 whitespace-nowrap"
      style={{ background: bg, color: fg }}
    >
      {category || 'N/A'}
    </span>
  )
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score)) * 100
  const hue = score > 0.7 ? 142 : score > 0.4 ? 45 : 0
  return (
    <div
      className="flex items-center gap-2"
      role="progressbar"
      aria-valuenow={score}
      aria-valuemin={0}
      aria-valuemax={1}
    >
      <div className="flex-1 h-3 rounded-base border border-border/30 bg-bg overflow-hidden" style={{ minWidth: 60 }}>
        <div className="h-full rounded-base" style={{ width: `${pct}%`, background: `hsl(${hue}, 70%, 55%)` }} />
      </div>
      <span className="text-xs font-heading text-fg/70 w-8 text-right">{score.toFixed(2)}</span>
    </div>
  )
}

function GraphLink({ search, children }: { search: string; children: React.ReactNode }) {
  const setPendingSearch = useStore((s) => s.setPendingSearch)
  return (
    <Link
      to="/graph"
      onClick={() => setPendingSearch(search)}
      className="text-fg/70 hover:text-main hover:underline cursor-pointer transition-colors break-anywhere"
      title="View in Graph Explorer"
    >
      {children}
      <span className="text-[9px] text-main/40 ml-1">→ Graph</span>
    </Link>
  )
}

function IndexView() {
  const graph = useStore((s) => s.graph)

  if (!graph) {
    return <OnboardingSection />
  }

  return <DashboardContent />
}

/* ---------- Onboarding (file picker / server connect) ---------- */

function OnboardingSection() {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [serverUrl, setServerUrl] = useState('http://localhost:8765')
  const [isDragging, setIsDragging] = useState(false)
  const isLoading = useStore((s) => s.isLoading)
  const error = useStore((s) => s.error)

  const handleFileSelect = useCallback(async () => {
    const files = fileInputRef.current?.files
    if (!files || files.length === 0) return
    await loadFromFiles(files)
  }, [])

  const handleServerConnect = useCallback(async () => {
    const url = serverUrl.replace(/\/+$/, '')
    if (!url) return
    await loadFromServer(url)
  }, [serverUrl])

  const handleLoadDemo = useCallback(async () => {
    await loadFromServer('')
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    const files = e.dataTransfer.files
    if (files.length > 0) {
      await loadFromFiles(files)
    }
  }, [])

  return (
    <div
      role="application"
      className="flex flex-col items-center justify-center h-full p-8 view-enter"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragging && (
        <div className="drag-overlay">
          <div className="drag-overlay-inner">
            <p className="text-2xl font-heading">Drop .code-context files here</p>
          </div>
        </div>
      )}

      <div className="w-full max-w-lg space-y-8">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-heading tracking-tight">Code Context Visualizer</h1>
          <p className="text-fg/50 mt-2 font-base">Load analysis artifacts to explore your codebase</p>
        </div>

        {/* Error display */}
        {error && (
          <div className="rounded-base border-2 border-border bg-chart-2/10 p-4 text-sm font-base text-chart-2">
            {error}
          </div>
        )}

        {/* File picker */}
        <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-6 space-y-4">
          <h2 className="font-heading text-lg">Load from Files</h2>
          <p className="text-sm text-fg/50 font-base">
            Select a .code-context directory or individual artifact files (code_graph.json, CONTEXT.md, etc.)
          </p>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".json,.md,.txt"
            onChange={handleFileSelect}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="w-full px-4 py-2.5 bg-main text-main-fg rounded-base border-2 border-border shadow-neo neo-pressable font-heading text-sm disabled:opacity-50 disabled:pointer-events-none"
          >
            {isLoading ? (
              <span className="inline-flex items-center gap-2">
                <span className="inline-block w-4 h-4 border-2 border-main-fg/30 border-t-main-fg rounded-full animate-spin" />
                Loading...
              </span>
            ) : (
              'Choose Files'
            )}
          </button>
        </div>

        {/* Server connection */}
        <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-6 space-y-4">
          <h2 className="font-heading text-lg">Connect to Server</h2>
          <p className="text-sm text-fg/50 font-base">Enter the URL of a running code-context-agent server</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={serverUrl}
              onChange={(e) => setServerUrl(e.target.value)}
              placeholder="http://localhost:8765"
              disabled={isLoading}
              className="flex-1 px-3 py-2 text-sm rounded-base border-2 border-border bg-bg text-fg placeholder:text-fg/30 neo-focus font-base disabled:opacity-50"
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleServerConnect()
              }}
            />
            <button
              type="button"
              onClick={handleServerConnect}
              disabled={isLoading}
              className="px-4 py-2 bg-main text-main-fg rounded-base border-2 border-border shadow-neo neo-pressable font-heading text-sm disabled:opacity-50 disabled:pointer-events-none"
            >
              Connect
            </button>
          </div>
        </div>

        {/* Demo data */}
        <div className="text-center">
          <button
            type="button"
            onClick={handleLoadDemo}
            disabled={isLoading}
            className="px-6 py-2 rounded-base border-2 border-border shadow-neo neo-pressable font-base text-sm bg-bg2 hover:bg-main/20 transition-colors disabled:opacity-50 disabled:pointer-events-none"
          >
            Load Demo Data
          </button>
        </div>

        {/* Drop zone hint */}
        <p className="text-center text-xs text-fg/30 font-base">
          You can also drag and drop files anywhere on this page
        </p>
      </div>
    </div>
  )
}

/* ---------- Dashboard content ---------- */

function DashboardContent() {
  const graph = useStore((s) => s.graph)!
  const analysisResult = useStore((s) => s.analysisResult)
  const nodeTypes = useStore((s) => s.nodeTypes)
  const edgeTypes = useStore((s) => s.edgeTypes)

  const codeHealth = analysisResult?.code_health ?? null
  const risks = analysisResult?.risks ?? []
  const businessLogicItems = analysisResult?.business_logic_items ?? []

  const nodeData = useMemo(
    () =>
      Object.entries(nodeTypes).map(([type, count]) => ({
        label: type,
        value: count,
        color: NODE_COLORS[type] ?? '#6a6a86',
      })),
    [nodeTypes],
  )
  const edgeData = useMemo(
    () =>
      Object.entries(edgeTypes).map(([type, count]) => ({
        label: type,
        value: count,
        color: EDGE_COLORS[type] ?? '#6a6a86',
      })),
    [edgeTypes],
  )
  const healthScore = codeHealth ? Math.max(0, Math.min(100, 100 - (codeHealth.duplication_percentage || 0))) : null

  return (
    <div className="p-6 space-y-6 bg-bg min-h-full view-enter">
      <h1 className="text-2xl font-heading text-fg">Dashboard</h1>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Nodes" value={fmt(graph.nodes.length)} color="#60a5fa" />
        <StatCard title="Total Edges" value={fmt(graph.links.length)} color="#a78bfa" />
        <StatCard
          title="Files Analyzed"
          value={analysisResult?.total_files_analyzed != null ? fmt(analysisResult.total_files_analyzed) : '--'}
          color="#34d399"
        />
        <StatCard title="Analysis Mode" value={analysisResult?.analysis_mode ?? '--'} color="#f472b6" />
      </div>

      {/* Distribution Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
          <h3 className="text-sm font-heading uppercase tracking-wide text-fg/60 mb-3">Node Type Distribution</h3>
          <NeoBarChart data={nodeData} maxBars={10} height={200} />
        </div>
        <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
          <h3 className="text-sm font-heading uppercase tracking-wide text-fg/60 mb-3">Edge Type Distribution</h3>
          <NeoBarChart data={edgeData} maxBars={10} height={200} />
        </div>
      </div>

      {/* Code Health + Risks */}
      {(healthScore != null || risks.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {healthScore != null && (
            <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
              <h3 className="text-sm font-heading uppercase tracking-wide text-fg/60 mb-3">Code Health</h3>
              <div className="flex justify-center">
                <Gauge value={Math.round(healthScore)} max={100} label="Health Score" />
              </div>
              <div className="grid grid-cols-2 gap-2 mt-4">
                <StatCard
                  title="Duplication"
                  value={`${(codeHealth?.duplication_percentage ?? 0).toFixed(1)}%`}
                  color="#f87171"
                />
                <StatCard title="Clone Groups" value={fmt(codeHealth?.total_clone_groups ?? 0)} color="#fbbf24" />
                <StatCard title="Unused Symbols" value={fmt(codeHealth?.unused_symbol_count ?? 0)} color="#fb923c" />
                <StatCard title="Code Smells" value={fmt(codeHealth?.code_smell_count ?? 0)} color="#a78bfa" />
              </div>
            </div>
          )}
          {risks.length > 0 && <RiskSummary risks={risks} />}
        </div>
      )}

      {/* Business Logic Table */}
      {businessLogicItems.length > 0 && (
        <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
          <h3 className="text-sm font-heading uppercase tracking-wide text-fg/60 mb-3">Business Logic</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left table-fixed">
              <thead>
                <tr className="border-b-2 border-border">
                  {['Rank', 'Name', 'Role', 'Location', 'Score', 'Category'].map((h) => (
                    <th key={h} className="py-2 px-3 text-xs font-heading uppercase tracking-wide text-fg/50">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {businessLogicItems.map((item, i) => (
                  <tr key={i} className="border-b border-border/20 hover:bg-bg/50 transition-colors">
                    <td className="py-2 px-3 text-xs font-heading text-fg/70 text-center">{item.rank ?? '--'}</td>
                    <td className="py-2 px-3 text-xs font-heading break-anywhere">
                      <GraphLink search={item.name}>{item.name || '--'}</GraphLink>
                    </td>
                    <td className="py-2 px-3 text-xs font-base text-fg/70 max-w-xs truncate-line">
                      {item.role || '--'}
                    </td>
                    <td className="py-2 px-3 text-xs font-base text-fg/50 break-anywhere">
                      <GraphLink search={shortPath(item.location)}>{shortPath(item.location)}</GraphLink>
                    </td>
                    <td className="py-2 px-3 text-xs" style={{ minWidth: 100 }}>
                      <ScoreBar score={item.score ?? 0} />
                    </td>
                    <td className="py-2 px-3">
                      <CategoryBadge category={item.category} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function RiskSummary({ risks }: { risks: ArchitecturalRisk[] }) {
  const [expanded, setExpanded] = useState(false)
  const setPendingSearch = useStore((s) => s.setPendingSearch)
  const severityOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }
  const sorted = [...risks].sort((a, b) => (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3))
  const counts: Record<string, number> = {}
  for (const risk of risks)
    counts[(risk.severity || 'low').toLowerCase()] = (counts[(risk.severity || 'low').toLowerCase()] || 0) + 1
  const visible = sorted.slice(0, 5)
  const overflow = sorted.slice(5)

  return (
    <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
      <h3 className="text-sm font-heading uppercase tracking-wide text-fg/60 mb-3">Risk Summary</h3>
      <div className="flex gap-4 mb-4">
        {Object.entries(counts)
          .filter(([, c]) => c > 0)
          .map(([sev, count]) => (
            <div key={sev} className="flex items-center gap-2">
              <SeverityBadge severity={sev} />
              <span className="text-sm font-heading text-fg">{count}</span>
            </div>
          ))}
      </div>
      <div className="space-y-0">
        {[...visible, ...(expanded ? overflow : [])].map((risk, i) => (
          <div key={i} className="flex items-start gap-2 py-2 border-b border-border/20 last:border-b-0">
            <SeverityBadge severity={risk.severity || 'low'} />
            <div className="flex-1">
              <p className="text-xs text-fg/80 font-base leading-relaxed">{risk.description}</p>
              {risk.location && (
                <Link
                  to="/graph"
                  onClick={() => setPendingSearch(shortPath(risk.location!))}
                  className="text-[10px] text-fg/50 hover:text-main hover:underline cursor-pointer mt-0.5 inline-block"
                >
                  {shortPath(risk.location)}
                </Link>
              )}
            </div>
          </div>
        ))}
      </div>
      {overflow.length > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-main hover:underline cursor-pointer mt-2 font-base"
        >
          {expanded ? '− Show fewer' : `+ ${overflow.length} more risks`}
        </button>
      )}
    </div>
  )
}
