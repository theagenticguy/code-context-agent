// insights.js — Deep dive into analysis results: refactoring candidates, code health, phase timings.
// Uses D3 (window.d3) for the phase timing waterfall chart.

import { store } from '../store.js';
import { statCard } from '../components/stat-card.js';
import { gaugeChart } from '../components/gauge.js';
import { SEVERITY_COLORS } from '../colors.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TYPE_COLORS = {
  extract_helper: '#60a5fa',
  inline_wrapper: '#4ade80',
  dead_code: '#f87171',
  code_smell: '#fbbf24',
};

const TYPE_LABELS = {
  extract_helper: 'Extract Helper',
  inline_wrapper: 'Inline Wrapper',
  dead_code: 'Dead Code',
  code_smell: 'Code Smell',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Shorten a file path for display (keep last 2-3 segments).
 * @param {string} filePath
 * @returns {string}
 */
function truncatePath(filePath) {
  const parts = filePath.split(/[/\\]/);
  if (parts.length <= 3) return filePath;
  return '../' + parts.slice(-3).join('/');
}

/**
 * Build a colored badge HTML string.
 * @param {string} text
 * @param {string} bg - Background color hex
 * @param {string} [fg='#000'] - Text color hex
 * @returns {string}
 */
function badge(text, bg, fg = '#000') {
  return `<span class="inline-flex items-center px-2 py-0.5 text-xs font-heading rounded-base border-2 border-border" style="background: ${bg}; color: ${fg}">${text}</span>`;
}

// ---------------------------------------------------------------------------
// Section: Summary Callout
// ---------------------------------------------------------------------------

/**
 * @param {object} result - The analysisResult object
 * @returns {string} HTML
 */
function renderSummary(result) {
  const statusColor = result.status === 'completed' ? '#4ade80'
    : result.status === 'partial' ? '#fbbf24'
    : '#f87171';

  const statusLabel = result.status.charAt(0).toUpperCase() + result.status.slice(1);

  const modeLabel = (result.analysis_mode || 'standard').charAt(0).toUpperCase()
    + (result.analysis_mode || 'standard').slice(1);

  return `
    <section class="mb-8">
      <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-6">
        <div class="flex items-center gap-3 mb-3 flex-wrap">
          <h2 class="font-heading text-xl">Analysis Summary</h2>
          ${badge(statusLabel, statusColor)}
          ${badge(modeLabel, 'var(--main)', 'var(--main-foreground)')}
          ${badge(result.total_files_analyzed + ' files', '#e2e8f0', '#1e293b')}
        </div>
        <p class="text-sm text-fg/80 leading-relaxed font-base">${result.summary || 'No summary available.'}</p>
      </div>
    </section>`;
}

// ---------------------------------------------------------------------------
// Section: Refactoring Candidates
// ---------------------------------------------------------------------------

/**
 * Render a single refactoring candidate card.
 * @param {object} candidate - RefactoringCandidate
 * @param {number} maxScore - Maximum score across all candidates (for bar scaling)
 * @returns {string} HTML
 */
function renderCandidate(candidate, maxScore) {
  const color = TYPE_COLORS[candidate.type] || '#6a6a86';
  const label = TYPE_LABELS[candidate.type] || candidate.type;
  const barPct = maxScore > 0 ? (candidate.score / maxScore) * 100 : 0;

  const fileList = (candidate.files || [])
    .slice(0, 5)
    .map((f) => `<span class="text-xs text-fg/60 font-mono truncate-line block" title="${f}">${truncatePath(f)}</span>`)
    .join('');

  const moreFiles = (candidate.files || []).length > 5
    ? `<span class="text-xs text-fg/40">+${candidate.files.length - 5} more</span>`
    : '';

  return `
    <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4 hover:translate-x-shadow-x hover:translate-y-shadow-y hover:shadow-none transition-all duration-100">
      <div class="flex items-center gap-2 mb-2 flex-wrap">
        ${badge(label, color)}
        <span class="text-xs text-fg/50 ml-auto font-heading">score: ${candidate.score.toFixed(1)}</span>
      </div>
      <p class="text-sm font-base text-fg/90 mb-2">${candidate.pattern}</p>
      <div class="mb-3">
        <div class="h-3 rounded-base border border-border/30 bg-bg overflow-hidden">
          <div class="h-full rounded-base transition-all duration-300" style="width: ${barPct.toFixed(1)}%; background: ${color}"></div>
        </div>
      </div>
      <div class="flex gap-4 mb-2 text-xs">
        <span class="text-fg/70"><span class="font-heading">${candidate.occurrence_count}</span> occurrences</span>
        <span class="text-fg/70"><span class="font-heading">${candidate.duplicated_lines}</span> duplicated lines</span>
      </div>
      <div class="space-y-0.5">
        ${fileList}
        ${moreFiles}
      </div>
    </div>`;
}

/**
 * @param {object[]} candidates - RefactoringCandidate[]
 * @returns {string} HTML
 */
function renderRefactoringCandidates(candidates) {
  if (!candidates || candidates.length === 0) {
    return `
      <section class="mb-8">
        <h2 class="font-heading text-lg mb-4">Refactoring Candidates</h2>
        <div class="rounded-base border-2 border-border bg-bg2 p-6 text-center text-fg/40 text-sm">
          No refactoring candidates identified.
        </div>
      </section>`;
  }

  // Sort by score descending
  const sorted = [...candidates].sort((a, b) => (b.score || 0) - (a.score || 0));
  const maxScore = sorted.reduce((m, c) => Math.max(m, c.score || 0), 0) || 1;

  return `
    <section class="mb-8">
      <h2 class="font-heading text-lg mb-4">Refactoring Candidates <span class="text-sm text-fg/50 font-base">(${sorted.length})</span></h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        ${sorted.map((c) => renderCandidate(c, maxScore)).join('')}
      </div>
    </section>`;
}

// ---------------------------------------------------------------------------
// Section: Code Health Detail
// ---------------------------------------------------------------------------

/**
 * @param {object} health - CodeHealthMetrics
 * @returns {string} HTML
 */
function renderCodeHealth(health) {
  if (!health) {
    return `
      <section class="mb-8">
        <h2 class="font-heading text-lg mb-4">Code Health</h2>
        <div class="rounded-base border-2 border-border bg-bg2 p-6 text-center text-fg/40 text-sm">
          No code health data available.
        </div>
      </section>`;
  }

  const dupPct = health.duplication_percentage ?? 0;
  const cloneGroups = health.total_clone_groups ?? 0;
  const unusedSymbols = health.unused_symbol_count ?? 0;
  const codeSmells = health.code_smell_count ?? 0;
  const healthScore = Math.round(100 - dupPct);

  // Color thresholds
  const dupColor = dupPct > 15 ? SEVERITY_COLORS.high : dupPct > 5 ? SEVERITY_COLORS.medium : SEVERITY_COLORS.low;
  const cloneColor = cloneGroups > 10 ? SEVERITY_COLORS.high : cloneGroups > 3 ? SEVERITY_COLORS.medium : SEVERITY_COLORS.low;
  const unusedColor = unusedSymbols > 20 ? SEVERITY_COLORS.high : unusedSymbols > 5 ? SEVERITY_COLORS.medium : SEVERITY_COLORS.low;
  const smellColor = codeSmells > 10 ? SEVERITY_COLORS.high : codeSmells > 3 ? SEVERITY_COLORS.medium : SEVERITY_COLORS.low;

  const cards = [
    statCard({ title: 'Duplication', value: dupPct.toFixed(1) + '%', subtitle: 'Percentage of duplicated code', color: dupColor }),
    statCard({ title: 'Clone Groups', value: cloneGroups, subtitle: 'Distinct code clone groups', color: cloneColor }),
    statCard({ title: 'Unused Symbols', value: unusedSymbols, subtitle: 'Potentially dead exports', color: unusedColor }),
    statCard({ title: 'Code Smells', value: codeSmells, subtitle: 'Detected code smells', color: smellColor }),
  ].join('');

  const gauge = gaugeChart({
    value: healthScore,
    max: 100,
    label: 'Health Score',
    zones: [
      { from: 0, to: 40, color: SEVERITY_COLORS.high },
      { from: 40, to: 70, color: SEVERITY_COLORS.medium },
      { from: 70, to: 100, color: SEVERITY_COLORS.low },
    ],
  });

  return `
    <section class="mb-8">
      <h2 class="font-heading text-lg mb-4">Code Health</h2>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        ${cards}
      </div>
      <div class="flex justify-center">
        <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4 inline-block">
          ${gauge}
        </div>
      </div>
    </section>`;
}

// ---------------------------------------------------------------------------
// Section: Phase Timings Waterfall (D3)
// ---------------------------------------------------------------------------

/**
 * Build the D3 waterfall chart for phase timings.
 * @param {HTMLElement} container - The DOM element to render into
 * @param {object[]} timings - PhaseTimingItem[]
 * @returns {() => void} cleanup function
 */
function renderPhaseTimingsD3(container, timings) {
  const d3 = window.d3;
  if (!d3 || !timings || timings.length === 0) {
    container.innerHTML = `
      <div class="rounded-base border-2 border-border bg-bg2 p-6 text-center text-fg/40 text-sm">
        No phase timing data available.
      </div>`;
    return () => {};
  }

  // Compute cumulative start times
  let cumulative = 0;
  const phases = timings.map((t) => {
    const start = cumulative;
    cumulative += t.duration_seconds;
    return { ...t, start, end: cumulative };
  });
  const totalDuration = cumulative;

  // Chart dimensions
  const margin = { top: 20, right: 30, bottom: 40, left: 160 };
  const barHeight = 36;
  const gap = 8;
  const width = Math.max(600, container.clientWidth - 32);
  const height = margin.top + margin.bottom + phases.length * (barHeight + gap);

  // Chart color gradient from chart-1 to chart-5
  const chartColors = [
    getComputedStyle(document.documentElement).getPropertyValue('--chart-1').trim(),
    getComputedStyle(document.documentElement).getPropertyValue('--chart-2').trim(),
    getComputedStyle(document.documentElement).getPropertyValue('--chart-3').trim(),
    getComputedStyle(document.documentElement).getPropertyValue('--chart-4').trim(),
    getComputedStyle(document.documentElement).getPropertyValue('--chart-5').trim(),
  ].filter(Boolean);

  // Fallback colors if CSS variables are empty
  const fallbackColors = ['#60a5fa', '#f87171', '#fbbf24', '#4ade80', '#a78bfa'];
  const colors = chartColors.length >= 5 ? chartColors : fallbackColors;

  // Build a piecewise color scale: map phase indices [0..n-1] to 5 gradient stops
  const maxIdx = Math.max(phases.length - 1, 1);
  const colorScale = d3.scaleLinear()
    .domain(colors.map((_, i) => (i / (colors.length - 1)) * maxIdx))
    .range(colors)
    .interpolate(d3.interpolateRgb)
    .clamp(true);

  // Create SVG
  container.innerHTML = '';
  const svg = d3.select(container)
    .append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('width', width)
    .attr('height', height)
    .attr('class', 'text-fg');

  // Scales
  const xScale = d3.scaleLinear()
    .domain([0, totalDuration || 1])
    .range([margin.left, width - margin.right]);

  const yScale = d3.scaleBand()
    .domain(phases.map((_, i) => i))
    .range([margin.top, height - margin.bottom])
    .padding(0.15);

  // X axis
  svg.append('g')
    .attr('transform', `translate(0, ${height - margin.bottom})`)
    .call(d3.axisBottom(xScale).ticks(6).tickFormat((d) => d.toFixed(1) + 's'))
    .call((g) => {
      g.selectAll('text')
        .attr('fill', 'currentColor')
        .style('font-size', '10px')
        .style('font-weight', '500');
      g.selectAll('line').attr('stroke', 'currentColor').attr('opacity', 0.2);
      g.select('.domain').attr('stroke', 'currentColor').attr('opacity', 0.3);
    });

  // X axis label
  svg.append('text')
    .attr('x', (margin.left + width - margin.right) / 2)
    .attr('y', height - 4)
    .attr('text-anchor', 'middle')
    .attr('fill', 'currentColor')
    .attr('opacity', 0.5)
    .style('font-size', '10px')
    .text('Cumulative Time (seconds)');

  // Grid lines
  svg.append('g')
    .selectAll('line')
    .data(xScale.ticks(6))
    .join('line')
    .attr('x1', (d) => xScale(d))
    .attr('x2', (d) => xScale(d))
    .attr('y1', margin.top)
    .attr('y2', height - margin.bottom)
    .attr('stroke', 'currentColor')
    .attr('opacity', 0.06);

  // Phase bars
  const bars = svg.selectAll('.phase-bar')
    .data(phases)
    .join('g')
    .attr('class', 'phase-bar');

  // Bar rectangles
  bars.append('rect')
    .attr('x', (d) => xScale(d.start))
    .attr('y', (_, i) => yScale(i))
    .attr('width', (d) => Math.max(2, xScale(d.end) - xScale(d.start)))
    .attr('height', yScale.bandwidth())
    .attr('rx', 3)
    .attr('fill', (_, i) => colorScale(i))
    .attr('stroke', 'currentColor')
    .attr('stroke-width', 1.5)
    .attr('opacity', 0.85);

  // Phase labels (left side)
  bars.append('text')
    .attr('x', margin.left - 8)
    .attr('y', (_, i) => yScale(i) + yScale.bandwidth() / 2)
    .attr('dy', '0.35em')
    .attr('text-anchor', 'end')
    .attr('fill', 'currentColor')
    .style('font-size', '11px')
    .style('font-weight', '600')
    .text((d) => d.name);

  // Duration labels inside bars
  bars.append('text')
    .attr('x', (d) => {
      const barWidth = xScale(d.end) - xScale(d.start);
      return barWidth > 60 ? xScale(d.start) + 8 : xScale(d.end) + 6;
    })
    .attr('y', (_, i) => yScale(i) + yScale.bandwidth() / 2)
    .attr('dy', '0.35em')
    .attr('text-anchor', 'start')
    .attr('fill', (d) => {
      const barWidth = xScale(d.end) - xScale(d.start);
      return barWidth > 60 ? '#000' : 'currentColor';
    })
    .style('font-size', '10px')
    .style('font-weight', '700')
    .text((d) => d.duration_seconds.toFixed(1) + 's');

  // Tool count badges
  bars.append('rect')
    .attr('x', (d) => {
      const barWidth = xScale(d.end) - xScale(d.start);
      return barWidth > 100 ? xScale(d.end) - 42 : xScale(d.end) + 4;
    })
    .attr('y', (_, i) => yScale(i) + 2)
    .attr('width', 38)
    .attr('height', 16)
    .attr('rx', 3)
    .attr('fill', 'currentColor')
    .attr('opacity', 0.12);

  bars.append('text')
    .attr('x', (d) => {
      const barWidth = xScale(d.end) - xScale(d.start);
      return barWidth > 100 ? xScale(d.end) - 23 : xScale(d.end) + 23;
    })
    .attr('y', (_, i) => yScale(i) + 10)
    .attr('dy', '0.1em')
    .attr('text-anchor', 'middle')
    .attr('fill', 'currentColor')
    .style('font-size', '9px')
    .style('font-weight', '600')
    .text((d) => d.tool_count + ' tools');

  // Return cleanup
  return () => {
    container.innerHTML = '';
  };
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function renderEmpty() {
  return `
    <div class="flex flex-col items-center justify-center h-full min-h-[400px] text-center p-8">
      <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-8 max-w-md">
        <div class="text-4xl mb-4">\u2605</div>
        <h2 class="font-heading text-xl mb-2">No Analysis Results</h2>
        <p class="text-sm text-fg/50 font-base leading-relaxed">
          No analysis results loaded. Run <code class="px-1.5 py-0.5 rounded-base border border-border bg-bg text-xs font-mono">code-context-agent analyze</code> to generate insights.
        </p>
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Main render
// ---------------------------------------------------------------------------

/**
 * Render the Insights view.
 * @param {HTMLElement} container - The main content area
 * @param {import('../store.js').Store} _store - The global store
 * @returns {() => void} cleanup function
 */
export function render(container, _store) {
  const result = store.get('analysisResult');

  if (!result) {
    container.innerHTML = renderEmpty();
    container.firstElementChild?.classList.add('view-enter');
    return () => {};
  }

  // Build the static HTML sections
  const html = `
    <div class="p-6 max-w-6xl mx-auto view-enter">
      <h1 class="font-heading text-2xl mb-6">Insights</h1>
      ${renderSummary(result)}
      ${renderRefactoringCandidates(result.refactoring_candidates)}
      ${renderCodeHealth(result.code_health)}
      <section class="mb-8">
        <h2 class="font-heading text-lg mb-4">Phase Timings</h2>
        <div id="phase-timings-chart" class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4 overflow-x-auto"></div>
      </section>
    </div>`;

  container.innerHTML = html;

  // Render D3 waterfall chart
  const chartContainer = container.querySelector('#phase-timings-chart');
  let chartCleanup = () => {};
  if (chartContainer) {
    chartCleanup = renderPhaseTimingsD3(chartContainer, result.phase_timings);
  }

  // Handle window resize for chart
  let resizeTimer = null;
  const onResize = () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (chartContainer && result.phase_timings?.length) {
        chartCleanup();
        chartCleanup = renderPhaseTimingsD3(chartContainer, result.phase_timings);
      }
    }, 200);
  };
  window.addEventListener('resize', onResize);

  // Subscribe to store changes for reactivity
  const unsub = store.on('analysisResult', () => {
    // Re-render the whole view on data change
    cleanup();
    render(container, _store);
  });

  // Cleanup function
  function cleanup() {
    chartCleanup();
    window.removeEventListener('resize', onResize);
    clearTimeout(resizeTimer);
    unsub();
  }

  return cleanup;
}
