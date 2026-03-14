/**
 * Dashboard view — executive summary with stats, tables, and charts.
 */
import { state, NODE_COLORS, EDGE_COLORS, SEVERITY_COLORS, showTooltip, hideTooltip } from './state.js';

export function renderDashboard() {
  const g = state.graph;
  const ar = state.analysisResult;

  renderStatCards(g, ar);
  renderBusinessLogic(ar);
  renderRisks(ar);
  renderNodeTypeChart();
  renderEdgeTypeChart();
}

// ── Stat Cards ───────────────────────────────────────────────────
function renderStatCards(g, ar) {
  const container = document.getElementById('stats-cards');
  const totalFiles = ar?.total_files_analyzed ?? (g ? new Set(g.nodes.map(n => n.filePath)).size : 0);
  const nodeCount = g?.nodes.length ?? ar?.graph_stats?.node_count ?? 0;
  const edgeCount = g?.links.length ?? ar?.graph_stats?.edge_count ?? 0;
  const moduleCount = ar?.graph_stats?.module_count ?? Object.keys(state.nodeTypes).length;
  const hotspotCount = ar?.graph_stats?.hotspot_count ?? 0;
  const riskCount = ar?.risks?.length ?? 0;

  const cards = [
    { label: 'Files', value: totalFiles.toLocaleString(), color: NODE_COLORS.file },
    { label: 'Graph Nodes', value: nodeCount.toLocaleString(), color: '#a78bfa' },
    { label: 'Graph Edges', value: edgeCount.toLocaleString(), color: '#22d3ee' },
    { label: 'Node Types', value: Object.keys(state.nodeTypes).length, color: NODE_COLORS.function },
    { label: 'Edge Types', value: Object.keys(state.edgeTypes).length, color: EDGE_COLORS.imports },
    { label: 'Risks', value: riskCount, color: riskCount > 0 ? SEVERITY_COLORS.medium : SEVERITY_COLORS.low },
  ];

  container.innerHTML = cards.map(c => `
    <div class="stat-card" style="--stat-color:${c.color}">
      <div class="stat-value">${c.value}</div>
      <div class="stat-label">${c.label}</div>
    </div>
  `).join('');

  // Subtitle
  const sub = document.getElementById('dashboard-subtitle');
  if (ar?.summary) {
    sub.textContent = ar.summary;
  } else if (g) {
    sub.textContent = `${nodeCount} nodes, ${edgeCount} edges across ${totalFiles} files`;
  }
}

// ── Business Logic Table ─────────────────────────────────────────
function renderBusinessLogic(ar) {
  const tbody = document.querySelector('#table-business-logic tbody');
  const badge = document.getElementById('bl-count');
  const items = ar?.business_logic_items || [];

  badge.textContent = items.length || '0';

  if (items.length === 0) {
    // Generate from graph data if no analysis result
    if (state.graph) {
      const topNodes = state.graph.nodes
        .filter(n => n.nodeType === 'function' || n.nodeType === 'method' || n.nodeType === 'class')
        .slice(0, 20)
        .map((n, i) => ({
          rank: i + 1,
          name: n.name,
          role: n.nodeType,
          location: `${shortPath(n.filePath)}:${n.lineStart}`,
          score: 0,
          category: n.metadata?.category || null,
        }));
      badge.textContent = topNodes.length;
      renderBLRows(tbody, topNodes);
    } else {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No data</td></tr>';
    }
    return;
  }

  renderBLRows(tbody, items);
}

function renderBLRows(tbody, items) {
  tbody.innerHTML = items.map(item => `
    <tr>
      <td><span class="badge">${item.rank}</span></td>
      <td class="cell-name">${esc(item.name)}</td>
      <td>${esc(item.role)}</td>
      <td class="cell-location">${esc(item.location)}</td>
      <td>
        <div class="score-bar">
          <div class="score-bar-track">
            <div class="score-bar-fill" style="width:${(item.score * 100).toFixed(0)}%"></div>
          </div>
          <span class="score-bar-value">${item.score.toFixed(2)}</span>
        </div>
      </td>
      <td>${item.category ? `<span class="category-badge" data-category="${esc(item.category)}">${esc(item.category)}</span>` : '<span class="text-muted">-</span>'}</td>
    </tr>
  `).join('');
}

// ── Risks ────────────────────────────────────────────────────────
function renderRisks(ar) {
  const container = document.getElementById('risks-list');
  const badge = document.getElementById('risk-count');
  const risks = ar?.risks || [];

  badge.textContent = risks.length || '0';

  if (risks.length === 0) {
    container.innerHTML = '<p class="text-muted">No risks identified</p>';
    return;
  }

  container.innerHTML = risks.map(r => `
    <div class="risk-item">
      <div class="risk-header">
        <span class="risk-severity ${r.severity}"></span>
        <span class="risk-description">${esc(r.description)}</span>
      </div>
      ${r.location ? `<div class="risk-location">${esc(r.location)}</div>` : ''}
      ${r.mitigation ? `<div class="risk-mitigation">${esc(r.mitigation)}</div>` : ''}
    </div>
  `).join('');
}

// ── Node Type Donut Chart (D3) ───────────────────────────────────
function renderNodeTypeChart() {
  const container = document.getElementById('chart-node-types');
  container.innerHTML = '';
  if (!state.graph) return;

  const data = Object.entries(state.nodeTypes).map(([type, count]) => ({
    type,
    count,
    color: NODE_COLORS[type] || '#6a6a86',
  }));

  renderDonut(container, data, 'type', 'count', d => d.color);
}

function renderEdgeTypeChart() {
  const container = document.getElementById('chart-edge-types');
  container.innerHTML = '';
  if (!state.graph) return;

  const data = Object.entries(state.edgeTypes).map(([type, count]) => ({
    type,
    count,
    color: EDGE_COLORS[type] || '#6a6a86',
  }));

  renderDonut(container, data, 'type', 'count', d => d.color);
}

function renderDonut(container, data, labelKey, valueKey, colorFn) {
  const w = 280, h = 200, r = 70;
  const svg = d3.select(container)
    .append('svg')
    .attr('width', w)
    .attr('height', h);

  const g = svg.append('g')
    .attr('transform', `translate(${r + 20},${h / 2})`);

  const pie = d3.pie().value(d => d[valueKey]).sort(null);
  const arc = d3.arc().innerRadius(r * 0.55).outerRadius(r);

  const arcs = g.selectAll('.arc')
    .data(pie(data))
    .enter()
    .append('g');

  arcs.append('path')
    .attr('d', arc)
    .attr('fill', d => colorFn(d.data))
    .attr('stroke', 'var(--bg-card)')
    .attr('stroke-width', 2)
    .style('opacity', 0.85)
    .style('cursor', 'pointer')
    .on('mouseover', function(event, d) {
      d3.select(this).style('opacity', 1).attr('stroke', 'var(--text-primary)');
      const pct = ((d.data[valueKey] / total) * 100).toFixed(1);
      showTooltip(event, `<div class="tt-label">${esc(d.data[labelKey])}</div><div class="tt-row">${d.data[valueKey]} &middot; ${pct}%</div>`);
    })
    .on('mouseout', function() {
      d3.select(this).style('opacity', 0.85).attr('stroke', 'var(--bg-card)');
      hideTooltip();
    });

  // Total in center
  const total = data.reduce((s, d) => s + d[valueKey], 0);
  g.append('text')
    .attr('text-anchor', 'middle')
    .attr('dy', '-0.1em')
    .attr('fill', 'var(--text-primary)')
    .attr('font-size', '22px')
    .attr('font-weight', '800')
    .text(total.toLocaleString());

  g.append('text')
    .attr('text-anchor', 'middle')
    .attr('dy', '1.2em')
    .attr('fill', 'var(--text-muted)')
    .attr('font-size', '13px')
    .text('total');

  // Legend on the right
  const legend = svg.append('g')
    .attr('transform', `translate(${r * 2 + 50}, 20)`);

  data.forEach((d, i) => {
    const row = legend.append('g').attr('transform', `translate(0, ${i * 22})`);
    row.append('rect')
      .attr('width', 10).attr('height', 10).attr('rx', 2)
      .attr('fill', colorFn(d));
    row.append('text')
      .attr('x', 16).attr('y', 9)
      .attr('fill', 'var(--text-secondary)')
      .attr('font-size', '13px')
      .text(`${d[labelKey]} (${d[valueKey]})`);
  });
}

// ── Utils ────────────────────────────────────────────────────────
function shortPath(p) {
  if (!p) return '';
  const parts = p.split('/');
  return parts.slice(-3).join('/');
}

function esc(s) {
  if (!s) return '';
  const el = document.createElement('span');
  el.textContent = String(s);
  return el.innerHTML;
}
