/**
 * Hotspots & Foundations view — centrality visualizations.
 */
import { state, NODE_COLORS, computeDegreeCentrality, findEntryPoints, showTooltip, hideTooltip } from './state.js';

export function renderHotspots() {
  if (!state.graph) return;

  const ranked = computeDegreeCentrality();
  renderHotspotBars(ranked);
  renderFoundationBars(ranked);
  renderEntryPoints();
  renderDegreeDistribution(ranked);
}

// ── Hotspot Bars (top by total degree) ───────────────────────────
function renderHotspotBars(ranked) {
  const container = document.getElementById('hotspots-chart');
  container.innerHTML = '';

  const top = ranked.slice(0, 20);
  if (top.length === 0) {
    container.innerHTML = '<p class="text-muted">No hotspot data available</p>';
    return;
  }

  const maxDegree = top[0].totalDegree || 1;

  container.innerHTML = top.map((n, i) => {
    const pct = (n.totalDegree / maxDegree * 100).toFixed(0);
    const color = NODE_COLORS[n.nodeType] || '#6a6a86';
    return `
      <div class="hotspot-bar" data-idx="${i}">
        <span class="hotspot-name" title="${esc(n.id)}">
          <span class="node-type-dot" style="background:${color}"></span>
          ${esc(n.name)}
        </span>
        <div class="hotspot-track">
          <div class="hotspot-fill" style="width:${pct}%;background:${color}" data-value="${n.totalDegree}"></div>
        </div>
        <span class="hotspot-score">${n.totalDegree}</span>
      </div>
    `;
  }).join('');

  // Tooltips via event delegation
  container.addEventListener('mouseover', (event) => {
    const bar = event.target.closest('.hotspot-bar');
    if (!bar) return;
    const idx = parseInt(bar.dataset.idx, 10);
    const n = top[idx];
    if (!n) return;
    const color = NODE_COLORS[n.nodeType] || '#6a6a86';
    showTooltip(event,
      `<div class="tt-label">${esc(n.name)}</div>` +
      `<span class="tt-type" style="background:${color}20;color:${color}">${n.nodeType}</span>` +
      (n.filePath ? `<div class="tt-mono tt-muted">${esc(n.filePath.split('/').slice(-3).join('/'))}</div>` : '') +
      `<div class="tt-row" style="margin-top:3px">${n.inDegree} in &middot; ${n.outDegree} out &middot; ${n.totalDegree} total</div>`
    );
  });
  container.addEventListener('mouseout', (event) => {
    if (event.target.closest('.hotspot-bar')) hideTooltip();
  });
}

// ── Foundation Bars (top by in-degree - most depended upon) ──────
function renderFoundationBars(ranked) {
  const container = document.getElementById('foundations-chart');
  container.innerHTML = '';

  const byInDegree = [...ranked].sort((a, b) => b.inDegree - a.inDegree).slice(0, 20);
  if (byInDegree.length === 0) {
    container.innerHTML = '<p class="text-muted">No foundation data available</p>';
    return;
  }

  const maxIn = byInDegree[0].inDegree || 1;

  container.innerHTML = byInDegree.map((n, i) => {
    const pct = (n.inDegree / maxIn * 100).toFixed(0);
    const color = NODE_COLORS[n.nodeType] || '#6a6a86';
    return `
      <div class="hotspot-bar" data-idx="${i}">
        <span class="hotspot-name" title="${esc(n.id)}">
          <span class="node-type-dot" style="background:${color}"></span>
          ${esc(n.name)}
        </span>
        <div class="hotspot-track">
          <div class="hotspot-fill" style="width:${pct}%;background:linear-gradient(90deg, ${color}, ${color}88)" data-value="${n.inDegree}"></div>
        </div>
        <span class="hotspot-score">${n.inDegree}</span>
      </div>
    `;
  }).join('');

  // Tooltips via event delegation
  container.addEventListener('mouseover', (event) => {
    const bar = event.target.closest('.hotspot-bar');
    if (!bar) return;
    const idx = parseInt(bar.dataset.idx, 10);
    const n = byInDegree[idx];
    if (!n) return;
    const color = NODE_COLORS[n.nodeType] || '#6a6a86';
    showTooltip(event,
      `<div class="tt-label">${esc(n.name)}</div>` +
      `<span class="tt-type" style="background:${color}20;color:${color}">${n.nodeType}</span>` +
      (n.filePath ? `<div class="tt-mono tt-muted">${esc(n.filePath.split('/').slice(-3).join('/'))}</div>` : '') +
      `<div class="tt-row" style="margin-top:3px">${n.inDegree} in &middot; ${n.outDegree} out &middot; ${n.totalDegree} total</div>`
    );
  });
  container.addEventListener('mouseout', (event) => {
    if (event.target.closest('.hotspot-bar')) hideTooltip();
  });
}

// ── Entry Points ─────────────────────────────────────────────────
function renderEntryPoints() {
  const container = document.getElementById('entry-points-list');
  container.innerHTML = '';

  const entries = findEntryPoints();
  if (entries.length === 0) {
    container.innerHTML = '<p class="text-muted">No entry points detected. Requires call or import edges in the graph.</p>';
    return;
  }

  const isTopLevel = entries[0]?.entryReason === 'top-level';
  const notice = isTopLevel
    ? '<p class="text-muted" style="margin-bottom:10px">No call/import edges found. Showing top-level containers instead.</p>'
    : '';

  container.innerHTML = notice + entries.slice(0, 15).map(n => {
    const color = NODE_COLORS[n.nodeType] || '#6a6a86';
    return `
      <div class="entry-point-item">
        <span class="node-type-dot" style="background:${color}"></span>
        <span class="entry-point-name">${esc(n.name)}</span>
        <span class="entry-point-degree">${n.outDegree} ${isTopLevel ? 'members' : 'deps'}</span>
      </div>
    `;
  }).join('');
}

// ── Degree Distribution Chart ────────────────────────────────────
function renderDegreeDistribution(ranked) {
  const container = document.getElementById('degree-chart');
  container.innerHTML = '';

  if (ranked.length === 0) return;

  // Build histogram bins
  const degrees = ranked.map(n => n.totalDegree);
  const maxDeg = Math.max(...degrees);
  const binCount = Math.min(20, maxDeg + 1);
  const binSize = Math.max(1, Math.ceil((maxDeg + 1) / binCount));

  const bins = new Array(binCount).fill(0);
  for (const d of degrees) {
    const idx = Math.min(Math.floor(d / binSize), binCount - 1);
    bins[idx]++;
  }

  const w = 280, h = 160;
  const margin = { top: 10, right: 10, bottom: 30, left: 40 };
  const iw = w - margin.left - margin.right;
  const ih = h - margin.top - margin.bottom;

  const svg = d3.select(container)
    .append('svg')
    .attr('width', w)
    .attr('height', h);

  const g = svg.append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand()
    .domain(bins.map((_, i) => `${i * binSize}`))
    .range([0, iw])
    .padding(0.2);

  const y = d3.scaleLinear()
    .domain([0, Math.max(...bins)])
    .range([ih, 0]);

  // Bars
  g.selectAll('rect')
    .data(bins)
    .enter()
    .append('rect')
    .attr('x', (d, i) => x(`${i * binSize}`))
    .attr('y', d => y(d))
    .attr('width', x.bandwidth())
    .attr('height', d => ih - y(d))
    .attr('fill', 'var(--accent)')
    .attr('opacity', 0.7)
    .attr('rx', 2)
    .style('cursor', 'pointer')
    .on('mouseover', function(event, d) {
      d3.select(this).attr('opacity', 1);
      const i = bins.indexOf(d);
      const lo = i * binSize;
      const hi = lo + binSize - 1;
      showTooltip(event,
        `<div class="tt-label">Degree ${lo}${hi > lo ? '–' + hi : ''}</div>` +
        `<div class="tt-row">${d} node${d !== 1 ? 's' : ''}</div>`
      );
    })
    .on('mouseout', function() {
      d3.select(this).attr('opacity', 0.7);
      hideTooltip();
    });

  // X axis
  g.append('g')
    .attr('transform', `translate(0,${ih})`)
    .call(d3.axisBottom(x).tickValues(
      bins.map((_, i) => `${i * binSize}`).filter((_, i) => i % Math.ceil(binCount / 6) === 0)
    ))
    .selectAll('text')
    .attr('fill', 'var(--text-muted)')
    .attr('font-size', '11px');

  g.append('text')
    .attr('x', iw / 2)
    .attr('y', ih + 26)
    .attr('text-anchor', 'middle')
    .attr('fill', 'var(--text-muted)')
    .attr('font-size', '11px')
    .text('Degree');

  // Y axis
  g.append('g')
    .call(d3.axisLeft(y).ticks(4))
    .selectAll('text')
    .attr('fill', 'var(--text-muted)')
    .attr('font-size', '11px');

  // Style axes
  g.selectAll('.domain, .tick line').attr('stroke', 'var(--border-subtle)');
}

// ── Utils ────────────────────────────────────────────────────────
function esc(s) {
  if (!s) return '';
  const el = document.createElement('span');
  el.textContent = String(s);
  return el.innerHTML;
}
