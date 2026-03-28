import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'
import { EmptyState } from '../components/empty-state'
import { StatCard } from '../components/stat-card'
import { shortPath } from '../lib/graph-utils'
import { useStore } from '../store/use-store'
import type { PhaseTiming, RefactoringCandidate } from '../types'

export const Route = createFileRoute('/insights')({
  component: InsightsView,
})

/** Color palette for waterfall bars. */
const PHASE_COLORS = [
  '#60a5fa', // blue
  '#a78bfa', // purple
  '#34d399', // green
  '#fbbf24', // yellow
  '#f472b6', // pink
  '#fb923c', // orange
  '#22d3ee', // cyan
  '#ef4444', // red
]

function phaseColor(idx: number): string {
  return PHASE_COLORS[idx % PHASE_COLORS.length]
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}m ${secs.toFixed(0)}s`
}

function InsightsView() {
  const analysisResult = useStore((s) => s.analysisResult)
  const setPendingSearch = useStore((s) => s.setPendingSearch)
  const navigate = useNavigate()

  const phaseTimings = analysisResult?.phase_timings ?? []
  const refactoringCandidates = analysisResult?.refactoring_candidates ?? []

  // KPIs
  const stats = useMemo(() => {
    const totalDuration = phaseTimings.reduce((sum, p) => sum + p.duration_seconds, 0)
    const totalToolCalls = phaseTimings.reduce((sum, p) => sum + p.tool_count, 0)
    return {
      totalPhases: phaseTimings.length,
      totalDuration,
      totalToolCalls,
      refactoringCount: refactoringCandidates.length,
    }
  }, [phaseTimings, refactoringCandidates])

  // Max duration for scaling waterfall bars
  const maxDuration = useMemo(() => {
    if (phaseTimings.length === 0) return 1
    return Math.max(...phaseTimings.map((p) => p.duration_seconds))
  }, [phaseTimings])

  // Max score for scaling refactoring score bars
  const maxScore = useMemo(() => {
    if (refactoringCandidates.length === 0) return 1
    return Math.max(...refactoringCandidates.map((r) => r.score))
  }, [refactoringCandidates])

  // Navigate to graph with a file path
  const handleRefactoringClick = (candidate: RefactoringCandidate) => {
    const file = candidate.files[0]
    if (file) {
      setPendingSearch(shortPath(file))
      navigate({ to: '/graph' })
    }
  }

  if (!analysisResult) {
    return (
      <div className="p-6 view-enter h-full">
        <EmptyState
          icon="oo"
          title="No analysis results loaded"
          description="Load an analysis_result.json file to see phase timings and refactoring insights."
          actionLabel="Go to Dashboard"
          actionTo="/"
        />
      </div>
    )
  }

  return (
    <div className="p-6 view-enter flex flex-col gap-6 overflow-y-auto">
      <h1 className="text-2xl font-heading">Insights</h1>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="Total Phases" value={stats.totalPhases} color="#60a5fa" />
        <StatCard title="Total Duration" value={formatDuration(stats.totalDuration)} color="#a78bfa" />
        <StatCard title="Tool Calls" value={stats.totalToolCalls} color="#34d399" />
        <StatCard title="Refactoring Candidates" value={stats.refactoringCount} color="#fbbf24" />
      </div>

      {/* Phase Timing Waterfall */}
      {phaseTimings.length > 0 && (
        <section>
          <h2 className="text-lg font-heading mb-3">Phase Timing Waterfall</h2>
          <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-4 space-y-2">
            {phaseTimings.map((phase, idx) => (
              <PhaseBar key={phase.phase} phase={phase} color={phaseColor(idx)} maxDuration={maxDuration} />
            ))}
            {/* Total bar */}
            <div className="border-t border-border/30 pt-2 mt-2 flex items-center gap-3">
              <span className="text-xs font-heading text-fg/50 w-32 shrink-0 truncate">Total</span>
              <div className="flex-1 h-6 rounded-base bg-bg/50 border border-border/30 overflow-hidden">
                <div
                  className="h-full rounded-base"
                  style={{
                    width: '100%',
                    background: 'linear-gradient(90deg, #60a5fa, #a78bfa, #34d399)',
                    opacity: 0.4,
                  }}
                />
              </div>
              <span className="text-xs font-heading text-fg/60 w-16 text-right shrink-0">
                {formatDuration(stats.totalDuration)}
              </span>
              <span className="text-[10px] text-fg/40 w-20 text-right shrink-0">{stats.totalToolCalls} tools</span>
            </div>
          </div>
        </section>
      )}

      {/* Refactoring Candidates */}
      {refactoringCandidates.length > 0 && (
        <section>
          <h2 className="text-lg font-heading mb-3">Refactoring Candidates</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {refactoringCandidates
              .sort((a, b) => b.score - a.score)
              .map((candidate, idx) => (
                <RefactoringCard
                  key={idx}
                  candidate={candidate}
                  maxScore={maxScore}
                  onClick={() => handleRefactoringClick(candidate)}
                />
              ))}
          </div>
        </section>
      )}

      {/* Empty states for missing sections */}
      {phaseTimings.length === 0 && refactoringCandidates.length === 0 && (
        <div className="text-center text-fg/40 text-sm py-8 font-base">
          No phase timings or refactoring candidates found in the analysis result.
        </div>
      )}
    </div>
  )
}

/** Single phase bar in the waterfall chart. */
function PhaseBar({ phase, color, maxDuration }: { phase: PhaseTiming; color: string; maxDuration: number }) {
  const pct = maxDuration > 0 ? (phase.duration_seconds / maxDuration) * 100 : 0

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-heading text-fg/70 w-32 shrink-0 truncate" title={phase.name}>
        {phase.name}
      </span>
      <div className="flex-1 h-6 rounded-base bg-bg/50 border border-border/30 overflow-hidden">
        <div
          className="h-full rounded-base transition-all duration-500"
          style={{
            width: `${Math.max(pct, 2)}%`,
            background: color,
            opacity: 0.75,
          }}
        />
      </div>
      <span className="text-xs font-heading text-fg/60 w-16 text-right shrink-0">
        {formatDuration(phase.duration_seconds)}
      </span>
      <span className="text-[10px] text-fg/40 w-20 text-right shrink-0">{phase.tool_count} tools</span>
    </div>
  )
}

/** Refactoring candidate card. */
function RefactoringCard({
  candidate,
  maxScore,
  onClick,
}: {
  candidate: RefactoringCandidate
  maxScore: number
  onClick: () => void
}) {
  const scorePct = maxScore > 0 ? (candidate.score / maxScore) * 100 : 0
  const scoreColor = candidate.score >= 8 ? '#ef4444' : candidate.score >= 5 ? '#fbbf24' : '#4ade80'

  return (
    <button
      type="button"
      onClick={onClick}
      className="text-left rounded-base border-2 border-border shadow-neo bg-bg2 p-4 neo-pressable cursor-pointer transition-transform hover:-translate-y-0.5"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <p className="font-heading text-sm">{candidate.pattern}</p>
          <span
            className="inline-block text-[10px] px-1.5 py-0.5 rounded-base border border-border/50 mt-1"
            style={{
              background: `color-mix(in srgb, ${scoreColor} 15%, transparent)`,
              color: scoreColor,
            }}
          >
            {candidate.type}
          </span>
        </div>
        <span className="text-lg font-heading shrink-0" style={{ color: scoreColor }}>
          {candidate.score.toFixed(1)}
        </span>
      </div>

      {/* Score bar */}
      <div className="h-1.5 rounded-full bg-bg/50 border border-border/20 overflow-hidden mb-2">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${scorePct}%`, background: scoreColor }}
        />
      </div>

      {/* Details */}
      <div className="flex gap-4 text-[10px] text-fg/50">
        <span>{candidate.occurrence_count} occurrences</span>
        <span>{candidate.duplicated_lines} duplicated lines</span>
      </div>

      {/* Files */}
      {candidate.files.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {candidate.files.slice(0, 3).map((file) => (
            <span
              key={file}
              className="text-[10px] px-1.5 py-0.5 rounded bg-bg/50 text-fg/40 border border-border/20 truncate max-w-[180px]"
              title={file}
            >
              {shortPath(file)}
            </span>
          ))}
          {candidate.files.length > 3 && (
            <span className="text-[10px] text-fg/30">+{candidate.files.length - 3} more</span>
          )}
        </div>
      )}
    </button>
  )
}
