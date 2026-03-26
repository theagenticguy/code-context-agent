// hotspots.js — Centrality analysis view
// Shows degree centrality hotspots, entry points, degree distribution, and top files.

import { statCard } from '../components/stat-card.js';
import { barChart } from '../components/bar-chart.js';
import { NODE_COLORS, nodeColor } from '../colors.js';
import { computeDegreeCentrality, findEntryPoints, shortPath } from '../graph-utils.js';
import { escapeHtml } from '../escape.js';

/**
 * Render the hotspots / centrality analysis view.
 *
 * @param {HTMLElement} container - The #content element
 * @param {import('../store.js').Store} store - Global app store
 * @returns {() => void} Cleanup function
 */
export function render(container, store) {
  const graph = store.get('graph');

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------
  if (!graph || !graph.nodes || graph.nodes.length === 0) {
    container.innerHTML = `
      <div class="flex items-center justify-center h-full">
        <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-8 text-center max-w-md">
          <h2 class="text-xl font-heading mb-2">No Graph Data</h2>
          <p class="text-fg/60 font-base">
            Load a <code class="text-main">code_graph.json</code> file to see centrality analysis.
            Drag and drop it anywhere or use the file picker.
          </p>
        </div>
      </div>`;
    return () => {};
  }

  // -------------------------------------------------------------------------
  // Compute data
  // -------------------------------------------------------------------------
  const ranked = computeDegreeCentrality(graph);
  const totalNodes = ranked.length;
  const hotspotThreshold = Math.max(1, Math.ceil(totalNodes * 0.05));
  const hotspots = ranked.slice(0, hotspotThreshold);
  const entryPoints = findEntryPoints(graph);
  const avgDegree =
    totalNodes > 0
      ? (ranked.reduce((s, n) => s + n.totalDegree, 0) / totalNodes).toFixed(1)
      : '0';

  // Top 20 for bar chart
  const top20 = ranked.slice(0, 20).map((n) => ({
    ...n,
    label: shortPath(n.file_path) + ':' + n.name,
  }));

  // Entry points for bar chart
  const epData = entryPoints.map((n) => ({
    ...n,
    label: shortPath(n.file_path) + ':' + n.name,
  }));

  // -------------------------------------------------------------------------
  // Top Files — group nodes by file_path
  // -------------------------------------------------------------------------
  const fileMap = new Map();
  for (const n of ranked) {
    const fp = n.file_path || '(unknown)';
    if (!fileMap.has(fp)) {
      fileMap.set(fp, { filePath: fp, symbols: [], totalDegree: 0 });
    }
    const entry = fileMap.get(fp);
    entry.symbols.push(n);
    entry.totalDegree += n.totalDegree;
  }

  const topFiles = Array.from(fileMap.values())
    .map((f) => ({
      filePath: f.filePath,
      symbolCount: f.symbols.length,
      avgDegree: (f.totalDegree / f.symbols.length).toFixed(1),
      topSymbol: f.symbols.sort((a, b) => b.totalDegree - a.totalDegree)[0]?.name || '',
    }))
    .sort((a, b) => b.symbolCount - a.symbolCount)
    .slice(0, 30);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  container.innerHTML = `
    <div class="p-6 space-y-6 view-enter">

      <!-- Section header -->
      <div>
        <h1 class="text-2xl font-heading">Centrality Hotspots</h1>
        <p class="text-sm text-fg/60 font-base mt-1">
          Nodes with the highest degree centrality — the most connected symbols in your codebase.
        </p>
      </div>

      <!-- Section 1: KPI Cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4" id="hotspots-kpi"></div>

      <!-- Section 2: Two-column charts -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
          <h2 class="font-heading text-sm mb-3">Top 20 Hotspots</h2>
          <div id="hotspots-top20"></div>
        </div>
        <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
          <h2 class="font-heading text-sm mb-3">Entry Points</h2>
          <div id="hotspots-entry"></div>
        </div>
      </div>

      <!-- Section 3: Degree Distribution Histogram -->
      <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
        <h2 class="font-heading text-sm mb-3">Degree Distribution</h2>
        <div id="hotspots-histogram"></div>
      </div>

      <!-- Section 4: Top Files table -->
      <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4">
        <h2 class="font-heading text-sm mb-3">Top Files</h2>
        <div class="overflow-x-auto">
          <table class="w-full text-xs font-base" id="hotspots-files">
            <thead>
              <tr class="border-b-2 border-border text-left">
                <th class="py-2 pr-4 font-heading">File Path</th>
                <th class="py-2 pr-4 font-heading text-right">Symbols</th>
                <th class="py-2 pr-4 font-heading text-right">Avg Degree</th>
                <th class="py-2 font-heading">Top Symbol</th>
              </tr>
            </thead>
            <tbody id="hotspots-files-body"></tbody>
          </table>
        </div>
      </div>

    </div>`;

  // -------------------------------------------------------------------------
  // KPI cards
  // -------------------------------------------------------------------------
  const kpiContainer = container.querySelector('#hotspots-kpi');
  kpiContainer.innerHTML = [
    statCard({ title: 'Total Nodes', value: totalNodes.toLocaleString() }),
    statCard({
      title: 'Hotspots (Top 5%)',
      value: hotspots.length.toLocaleString(),
      color: NODE_COLORS.function,
    }),
    statCard({
      title: 'Entry Points',
      value: entryPoints.length.toLocaleString(),
      color: NODE_COLORS.class,
    }),
    statCard({ title: 'Avg Degree', value: avgDegree }),
  ].join('');

  // -------------------------------------------------------------------------
  // Bar charts
  // -------------------------------------------------------------------------
  const top20Container = container.querySelector('#hotspots-top20');
  top20Container.innerHTML = barChart({
    data: top20,
    labelKey: 'label',
    valueKey: 'totalDegree',
    colorFn: (item) => nodeColor(item.node_type),
    maxBars: 20,
  });

  const epContainer = container.querySelector('#hotspots-entry');
  epContainer.innerHTML = barChart({
    data: epData,
    labelKey: 'label',
    valueKey: 'outDegree',
    colorFn: (item) => nodeColor(item.node_type),
    maxBars: 20,
  });

  // -------------------------------------------------------------------------
  // Degree Distribution Histogram (D3)
  // -------------------------------------------------------------------------
  const histContainer = container.querySelector('#hotspots-histogram');
  const d3 = window.d3;

  if (d3 && ranked.length > 0) {
    const degrees = ranked.map((n) => n.totalDegree);

    const margin = { top: 16, right: 24, bottom: 36, left: 48 };
    const width = 800;
    const height = 240;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const bins = d3
      .bin()
      .thresholds(20)
      .domain(d3.extent(degrees))(degrees);

    const x = d3
      .scaleLinear()
      .domain([bins[0].x0, bins[bins.length - 1].x1])
      .range([0, innerW]);

    const y = d3
      .scaleLinear()
      .domain([0, d3.max(bins, (b) => b.length)])
      .nice()
      .range([innerH, 0]);

    const svg = d3
      .create('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('class', 'w-full')
      .attr('style', `max-height: ${height}px;`);

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Bars with neobrutalist 2px black border
    g.selectAll('rect')
      .data(bins)
      .join('rect')
      .attr('x', (d) => x(d.x0) + 1)
      .attr('y', (d) => y(d.length))
      .attr('width', (d) => Math.max(0, x(d.x1) - x(d.x0) - 2))
      .attr('height', (d) => innerH - y(d.length))
      .attr('fill', 'var(--chart-1)')
      .attr('stroke', 'var(--border)')
      .attr('stroke-width', 2)
      .attr('rx', 2);

    // X axis
    g.append('g')
      .attr('transform', `translate(0,${innerH})`)
      .call(d3.axisBottom(x).ticks(10))
      .call((axis) => {
        axis.select('.domain').attr('stroke', 'var(--border)').attr('stroke-width', 2);
        axis.selectAll('.tick line').attr('stroke', 'var(--border)');
        axis.selectAll('.tick text').attr('fill', 'var(--foreground)').attr('font-size', '11px');
      });

    // X axis label
    g.append('text')
      .attr('x', innerW / 2)
      .attr('y', innerH + 32)
      .attr('text-anchor', 'middle')
      .attr('fill', 'var(--foreground)')
      .attr('font-size', '11px')
      .attr('font-weight', 500)
      .text('Degree');

    // Y axis
    g.append('g')
      .call(d3.axisLeft(y).ticks(5))
      .call((axis) => {
        axis.select('.domain').attr('stroke', 'var(--border)').attr('stroke-width', 2);
        axis.selectAll('.tick line').attr('stroke', 'var(--border)');
        axis.selectAll('.tick text').attr('fill', 'var(--foreground)').attr('font-size', '11px');
      });

    // Y axis label
    g.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -innerH / 2)
      .attr('y', -36)
      .attr('text-anchor', 'middle')
      .attr('fill', 'var(--foreground)')
      .attr('font-size', '11px')
      .attr('font-weight', 500)
      .text('Count');

    histContainer.appendChild(svg.node());
  } else {
    histContainer.innerHTML =
      '<div class="text-xs text-fg/40 py-4 text-center font-base">No degree data available</div>';
  }

  // -------------------------------------------------------------------------
  // Top Files table rows
  // -------------------------------------------------------------------------
  const tbody = container.querySelector('#hotspots-files-body');
  tbody.innerHTML = topFiles
    .map(
      (f) => `
      <tr class="border-b border-border/30 hover:bg-main/5">
        <td class="py-1.5 pr-4 truncate-line max-w-xs" title="${escapeHtml(f.filePath)}">${escapeHtml(shortPath(f.filePath))}</td>
        <td class="py-1.5 pr-4 text-right font-heading">${f.symbolCount}</td>
        <td class="py-1.5 pr-4 text-right">${f.avgDegree}</td>
        <td class="py-1.5 text-fg/70">${escapeHtml(f.topSymbol)}</td>
      </tr>`
    )
    .join('');

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------
  return () => {
    container.innerHTML = '';
  };
}
