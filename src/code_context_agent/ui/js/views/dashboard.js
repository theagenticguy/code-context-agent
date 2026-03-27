// dashboard.js — Main dashboard overview view
// Renders KPI cards, distribution charts, code health gauge, risk summary,
// and business logic table using the store's graph + analysisResult data.

import { store } from '../store.js';
import { statCard } from '../components/stat-card.js';
import { barChart } from '../components/bar-chart.js';
import { gaugeChart } from '../components/gauge.js';
import { NODE_COLORS, EDGE_COLORS, SEVERITY_COLORS, NODE_TYPE_LABELS } from '../colors.js';
import { shortPath } from '../graph-utils.js';
import { escapeHtml, safeHtml, rawHtml, setHTML } from '../escape.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a number with locale-aware thousands separators.
 * @param {number} n
 * @returns {string}
 */
function fmt(n) {
  return (n ?? 0).toLocaleString();
}

/**
 * Build a colored severity badge.
 * @param {string} severity - high | medium | low
 * @returns {string} HTML string
 */
function severityBadge(severity) {
  const color = SEVERITY_COLORS[severity] || '#6a6a86';
  return `<span class="inline-flex items-center text-xs font-heading px-2 py-0.5 rounded-base border-2 border-border"
    style="background: ${color}20; color: ${color}">${severity}</span>`;
}

/**
 * Build a colored category badge for business logic items.
 * @param {string} category
 * @returns {string} HTML string
 */
function categoryBadge(category) {
  // Deterministic color from category string
  let hash = 0;
  for (let i = 0; i < (category || '').length; i++) {
    hash = category.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return `<span class="inline-flex items-center text-xs font-heading px-2 py-0.5 rounded-base border border-border/40 whitespace-nowrap"
    style="background: hsl(${hue}, 60%, 90%); color: hsl(${hue}, 60%, 30%)">${category || 'N/A'}</span>`;
}

/**
 * Build a small inline horizontal bar for a 0-1 score.
 * @param {number} score
 * @returns {string} HTML string
 */
function scoreBar(score) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const hue = score > 0.7 ? 142 : score > 0.4 ? 45 : 0; // green / yellow / red
  return `
    <div class="flex items-center gap-2">
      <div class="flex-1 h-3 rounded-base border border-border/30 bg-bg overflow-hidden" style="min-width: 60px;">
        <div class="h-full rounded-base" style="width: ${pct.toFixed(0)}%; background: hsl(${hue}, 70%, 55%)"></div>
      </div>
      <span class="text-xs font-heading text-fg/70 w-8 text-right">${score.toFixed(2)}</span>
    </div>`;
}

// ---------------------------------------------------------------------------
// Section builders
// ---------------------------------------------------------------------------

/**
 * Build empty-state HTML when no data is loaded.
 * @returns {string}
 */
function emptyState() {
  return `
    <div class="flex flex-col items-center justify-center h-full text-fg/50">
      <p class="text-xl font-heading">No data loaded</p>
      <p class="text-sm mt-2">Load files or connect to a server from the Landing page</p>
      <a href="#/" class="mt-4 px-4 py-2 bg-main text-main-fg rounded-base border-2 border-border shadow-neo neo-pressable font-base text-sm">Go to Landing</a>
    </div>`;
}

/**
 * Row 1: KPI stat cards (4 columns).
 * @param {object} graph
 * @param {object|null} analysisResult
 * @returns {string}
 */
function kpiRow(graph, analysisResult) {
  const nodeCount = graph ? graph.nodes.length : 0;
  const edgeCount = graph ? graph.links.length : 0;
  const filesAnalyzed = analysisResult?.total_files_analyzed ?? '--';
  const analysisMode = analysisResult?.analysis_mode ?? '--';

  return `
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      ${statCard({ title: 'Total Nodes', value: fmt(nodeCount), color: '#60a5fa' })}
      ${statCard({ title: 'Total Edges', value: fmt(edgeCount), color: '#a78bfa' })}
      ${statCard({ title: 'Files Analyzed', value: typeof filesAnalyzed === 'number' ? fmt(filesAnalyzed) : filesAnalyzed, color: '#34d399' })}
      ${statCard({ title: 'Analysis Mode', value: analysisMode, color: '#f472b6' })}
    </div>`;
}

/**
 * Row 2: Node and edge type distribution bar charts.
 * @param {Record<string, number>} nodeTypes
 * @param {Record<string, number>} edgeTypes
 * @returns {string}
 */
function distributionRow(nodeTypes, edgeTypes) {
  const nodeData = Object.entries(nodeTypes || {}).map(([type, count]) => ({ type, count }));
  const edgeData = Object.entries(edgeTypes || {}).map(([type, count]) => ({ type, count }));

  const nodeChartHtml = barChart({
    data: nodeData,
    labelKey: 'type',
    valueKey: 'count',
    colorFn: (item) => NODE_COLORS[item.type] || '#6a6a86',
  });

  const edgeChartHtml = barChart({
    data: edgeData,
    labelKey: 'type',
    valueKey: 'count',
    colorFn: (item) => EDGE_COLORS[item.type] || '#6a6a86',
  });

  return `
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
        <h3 class="text-sm font-heading uppercase tracking-wide text-fg/60 mb-3">Node Type Distribution</h3>
        ${nodeChartHtml}
      </div>
      <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
        <h3 class="text-sm font-heading uppercase tracking-wide text-fg/60 mb-3">Edge Type Distribution</h3>
        ${edgeChartHtml}
      </div>
    </div>`;
}

/**
 * Row 3 Left: Code health gauge with mini stat cards.
 * @param {object|null} codeHealth
 * @returns {string}
 */
function codeHealthSection(codeHealth) {
  if (!codeHealth) return '';

  const healthScore = Math.max(0, Math.min(100, 100 - (codeHealth.duplication_percentage || 0)));

  const gauge = gaugeChart({
    value: Math.round(healthScore),
    max: 100,
    label: 'Health Score',
    zones: [
      { from: 0, to: 40, color: '#f87171' },
      { from: 40, to: 70, color: '#fbbf24' },
      { from: 70, to: 100, color: '#4ade80' },
    ],
  });

  return `
    <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
      <h3 class="text-sm font-heading uppercase tracking-wide text-fg/60 mb-3">Code Health</h3>
      <div class="flex justify-center">${gauge}</div>
      <div class="grid grid-cols-2 gap-2 mt-4">
        ${statCard({ title: 'Duplication', value: (codeHealth.duplication_percentage ?? 0).toFixed(1) + '%', color: '#f87171' })}
        ${statCard({ title: 'Clone Groups', value: fmt(codeHealth.total_clone_groups ?? 0), color: '#fbbf24' })}
        ${statCard({ title: 'Unused Symbols', value: fmt(codeHealth.unused_symbol_count ?? 0), color: '#fb923c' })}
        ${statCard({ title: 'Code Smells', value: fmt(codeHealth.code_smell_count ?? 0), color: '#a78bfa' })}
      </div>
    </div>`;
}

/**
 * Row 3 Right: Risk summary with severity badges and top risks.
 * @param {Array<object>|null} risks
 * @returns {string}
 */
function riskSummarySection(risks) {
  if (!risks || risks.length === 0) return '';

  // Count by severity
  const counts = { high: 0, medium: 0, low: 0 };
  for (const risk of risks) {
    const sev = (risk.severity || 'low').toLowerCase();
    if (sev in counts) counts[sev]++;
    else counts.low++;
  }

  const severityBadges = Object.entries(counts)
    .filter(([, count]) => count > 0)
    .map(([sev, count]) => {
      const color = SEVERITY_COLORS[sev] || '#6a6a86';
      return `<div class="flex items-center gap-2">
        ${severityBadge(sev)}
        <span class="text-sm font-heading text-fg">${count}</span>
      </div>`;
    })
    .join('');

  // Top 5 risks (prefer high severity first)
  const severityOrder = { high: 0, medium: 1, low: 2 };
  const sorted = [...risks].sort(
    (a, b) => (severityOrder[a.severity] ?? 2) - (severityOrder[b.severity] ?? 2)
  );
  const top5 = sorted.slice(0, 5);

  const riskList = top5
    .map(
      (risk) => `
      <div class="flex items-start gap-2 py-2 border-b border-border/20 last:border-b-0">
        ${severityBadge(risk.severity || 'low')}
        <p class="text-xs text-fg/80 font-base leading-relaxed">${escapeHtml(risk.description || 'No description')}</p>
      </div>`
    )
    .join('');

  return `
    <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
      <h3 class="text-sm font-heading uppercase tracking-wide text-fg/60 mb-3">Risk Summary</h3>
      <div class="flex gap-4 mb-4">${severityBadges}</div>
      <div class="space-y-0">${riskList}</div>
      ${risks.length > 5 ? `<p class="text-xs text-fg/40 mt-2 font-base">+ ${risks.length - 5} more risks</p>` : ''}
    </div>`;
}

/**
 * Row 4: Business logic items table.
 * @param {Array<object>|null} items
 * @returns {string}
 */
function businessLogicTable(items) {
  if (!items || items.length === 0) return '';

  const rows = items
    .map(
      (item) => `
      <tr class="border-b border-border/20 hover:bg-bg/50 transition-colors">
        <td class="py-2 px-3 text-xs font-heading text-fg/70 text-center">${item.rank ?? '--'}</td>
        <td class="py-2 px-3 text-xs font-heading text-fg">${escapeHtml(item.name || '--')}</td>
        <td class="py-2 px-3 text-xs font-base text-fg/70">${escapeHtml(item.role || '--')}</td>
        <td class="py-2 px-3 text-xs font-base text-fg/50" title="${escapeHtml(item.location || '')}">${escapeHtml(shortPath(item.location || ''))}</td>
        <td class="py-2 px-3 text-xs" style="min-width: 100px;">${scoreBar(item.score ?? 0)}</td>
        <td class="py-2 px-3">${categoryBadge(item.category)}</td>
      </tr>`
    )
    .join('');

  return `
    <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
      <h3 class="text-sm font-heading uppercase tracking-wide text-fg/60 mb-3">Business Logic</h3>
      <div class="overflow-x-auto">
        <table class="w-full text-left">
          <thead>
            <tr class="border-b-2 border-border">
              <th class="py-2 px-3 text-xs font-heading uppercase tracking-wide text-fg/50 text-center">Rank</th>
              <th class="py-2 px-3 text-xs font-heading uppercase tracking-wide text-fg/50">Name</th>
              <th class="py-2 px-3 text-xs font-heading uppercase tracking-wide text-fg/50">Role</th>
              <th class="py-2 px-3 text-xs font-heading uppercase tracking-wide text-fg/50">Location</th>
              <th class="py-2 px-3 text-xs font-heading uppercase tracking-wide text-fg/50" style="min-width: 100px;">Score</th>
              <th class="py-2 px-3 text-xs font-heading uppercase tracking-wide text-fg/50">Category</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Main render
// ---------------------------------------------------------------------------

/**
 * Render the dashboard view into the given container.
 * @param {HTMLElement} container
 * @param {import('../store.js').Store} appStore
 * @returns {() => void} cleanup function
 */
export function render(container, appStore) {
  const graph = appStore.get('graph');

  // Empty state — no data loaded
  if (!graph) {
    setHTML(container, emptyState());
    // Re-render when graph becomes available
    const unsub = appStore.on('graph', () => render(container, appStore));
    return () => unsub();
  }

  const analysisResult = appStore.get('analysisResult') || {};
  const nodeTypes = appStore.get('nodeTypes') || {};
  const edgeTypes = appStore.get('edgeTypes') || {};

  const codeHealth = analysisResult.code_health || null;
  const risks = analysisResult.risks || null;
  const businessLogicItems = analysisResult.business_logic_items || null;

  // Build row 3 — code health + risk (conditional)
  const hasRow3Left = !!codeHealth;
  const hasRow3Right = risks && risks.length > 0;
  let row3Html = '';
  if (hasRow3Left || hasRow3Right) {
    if (hasRow3Left && hasRow3Right) {
      row3Html = `
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          ${codeHealthSection(codeHealth)}
          ${riskSummarySection(risks)}
        </div>`;
    } else {
      // Only one side — render it full-width
      row3Html = codeHealthSection(codeHealth) + riskSummarySection(risks);
    }
  }

  setHTML(container, safeHtml`
    <div class="p-6 space-y-6 bg-bg min-h-full">
      <h1 class="text-2xl font-heading text-fg">Dashboard</h1>
      ${rawHtml(kpiRow(graph, analysisResult))}
      ${rawHtml(distributionRow(nodeTypes, edgeTypes))}
      ${rawHtml(row3Html)}
      ${rawHtml(businessLogicTable(businessLogicItems))}
    </div>`);

  // Subscribe to store changes for live updates
  const unsubs = [
    appStore.on('graph', () => render(container, appStore)),
    appStore.on('analysisResult', () => render(container, appStore)),
    appStore.on('nodeTypes', () => render(container, appStore)),
    appStore.on('edgeTypes', () => render(container, appStore)),
  ];

  return () => unsubs.forEach((fn) => fn());
}
