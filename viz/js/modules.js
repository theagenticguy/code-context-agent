/**
 * Modules view — community/cluster visualization with D3 pack layout.
 */
import { state, NODE_COLORS, detectSimpleModules, showTooltip, hideTooltip } from './state.js';

export function renderModules() {
  if (!state.graph) return;

  const modules = detectSimpleModules();
  renderPackLayout(modules);
  renderModuleList(modules);
}

// ── Pack Layout ──────────────────────────────────────────────────
function renderPackLayout(modules) {
  const container = document.getElementById('modules-chart');
  container.innerHTML = '';
  const w = container.clientWidth || 700;
  const h = container.clientHeight || 500;

  const svg = d3.select(container)
    .append('svg')
    .attr('width', w)
    .attr('height', h);

  // Build hierarchy
  const root = {
    name: 'root',
    children: modules.map(m => ({
      name: m.path,
      module_id: m.module_id,
      children: m.members.map(n => ({
        name: n.name,
        value: 1,
        nodeType: n.nodeType,
        nodeData: n,
      })),
    })),
  };

  const hierarchy = d3.hierarchy(root)
    .sum(d => d.value || 0)
    .sort((a, b) => b.value - a.value);

  const pack = d3.pack()
    .size([w - 20, h - 20])
    .padding(8);

  const packed = pack(hierarchy);

  // Color scale for modules
  const moduleColors = d3.scaleOrdinal(d3.schemeTableau10);

  const zoom = d3.zoom()
    .scaleExtent([0.5, 5])
    .on('zoom', (event) => g.attr('transform', event.transform));

  svg.call(zoom);
  const g = svg.append('g').attr('transform', 'translate(10,10)');

  // Module circles (depth 1)
  const moduleNodes = packed.descendants().filter(d => d.depth === 1);
  const leafNodes = packed.descendants().filter(d => !d.children);

  // Module bubbles
  g.selectAll('.module-bubble')
    .data(moduleNodes)
    .enter()
    .append('circle')
    .attr('class', 'module-bubble')
    .attr('cx', d => d.x)
    .attr('cy', d => d.y)
    .attr('r', d => d.r)
    .attr('fill', (d, i) => moduleColors(i))
    .attr('fill-opacity', 0.08)
    .attr('stroke', (d, i) => moduleColors(i))
    .attr('stroke-opacity', 0.3)
    .attr('stroke-width', 1.5)
    .style('cursor', 'pointer')
    .on('click', (event, d) => showModuleDetail(d, moduleColors))
    .on('mouseover', function(event, d) {
      d3.select(this).attr('fill-opacity', 0.15).attr('stroke-opacity', 0.6);
      const members = d.leaves();
      const typeCounts = {};
      for (const leaf of members) {
        const t = leaf.data.nodeType || 'unknown';
        typeCounts[t] = (typeCounts[t] || 0) + 1;
      }
      const breakdown = Object.entries(typeCounts).map(([t, c]) =>
        `<span class="node-type-dot" style="background:${NODE_COLORS[t] || '#6a6a86'};display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:3px"></span>${t}: ${c}`
      ).join('<br>');
      showTooltip(event,
        `<div class="tt-label">${esc(d.data.name)}</div>` +
        `<div class="tt-muted" style="margin-bottom:3px">${members.length} members</div>` +
        breakdown
      );
    })
    .on('mouseout', function() {
      d3.select(this).attr('fill-opacity', 0.08).attr('stroke-opacity', 0.3);
      hideTooltip();
    });

  // Module labels
  g.selectAll('.module-label')
    .data(moduleNodes)
    .enter()
    .append('text')
    .attr('class', 'module-label')
    .attr('x', d => d.x)
    .attr('y', d => d.y - d.r + 14)
    .attr('text-anchor', 'middle')
    .attr('fill', (d, i) => moduleColors(i))
    .attr('font-size', d => Math.max(9, Math.min(13, d.r / 6)))
    .attr('font-weight', '700')
    .attr('pointer-events', 'none')
    .text(d => truncatePath(d.data.name, 30));

  // Leaf nodes
  g.selectAll('.leaf-node')
    .data(leafNodes)
    .enter()
    .append('circle')
    .attr('class', 'leaf-node')
    .attr('cx', d => d.x)
    .attr('cy', d => d.y)
    .attr('r', d => Math.max(2, d.r))
    .attr('fill', d => NODE_COLORS[d.data.nodeType] || '#6a6a86')
    .attr('fill-opacity', 0.7)
    .style('cursor', 'pointer')
    .on('mouseover', function(event, d) {
      d3.select(this).attr('fill-opacity', 1).attr('r', Math.max(3, d.r + 1));
      const color = NODE_COLORS[d.data.nodeType] || '#6a6a86';
      const nodeData = d.data.nodeData;
      showTooltip(event,
        `<div class="tt-label">${esc(d.data.name)}</div>` +
        `<span class="tt-type" style="background:${color}20;color:${color}">${d.data.nodeType}</span>` +
        (nodeData?.filePath ? `<div class="tt-mono tt-muted">${esc(nodeData.filePath.split('/').slice(-3).join('/'))}</div>` : '')
      );
    })
    .on('mouseout', function(event, d) {
      d3.select(this).attr('fill-opacity', 0.7).attr('r', Math.max(2, d.r));
      hideTooltip();
    });
}

// ── Module Detail Sidebar ────────────────────────────────────────
function showModuleDetail(d, colorScale) {
  const sidebar = document.getElementById('modules-detail');
  const modData = d.data;
  const members = d.leaves();
  const color = colorScale(d.parent.children.indexOf(d));

  // Count node types in module
  const typeCounts = {};
  for (const leaf of members) {
    const t = leaf.data.nodeType || 'unknown';
    typeCounts[t] = (typeCounts[t] || 0) + 1;
  }

  sidebar.innerHTML = `
    <div class="card">
      <div class="card-header" style="border-left: 3px solid ${color}">
        <h3>${esc(truncatePath(modData.name, 40))}</h3>
        <span class="badge">${members.length}</span>
      </div>
      <div class="card-body">
        <div style="margin-bottom:16px">
          <h4 style="font-size:var(--text-xs);text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:8px;font-weight:600">Composition</h4>
          ${Object.entries(typeCounts).map(([type, count]) => `
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
              <span class="node-type-dot" style="background:${NODE_COLORS[type] || '#6a6a86'}"></span>
              <span style="font-size:var(--text-xs);color:var(--text-secondary)">${type}</span>
              <span style="font-size:var(--text-xs);color:var(--text-muted);margin-left:auto">${count}</span>
            </div>
          `).join('')}
        </div>
        <div>
          <h4 style="font-size:var(--text-xs);text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:8px;font-weight:600">Members</h4>
          <div style="max-height:400px;overflow-y:auto">
            ${members.slice(0, 50).map(m => `
              <div style="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid var(--border-subtle)">
                <span class="node-type-dot" style="background:${NODE_COLORS[m.data.nodeType] || '#6a6a86'}"></span>
                <span style="font-family:var(--font-mono);font-size:var(--text-xs);color:var(--text-primary)">${esc(m.data.name)}</span>
              </div>
            `).join('')}
            ${members.length > 50 ? `<p class="text-muted" style="margin-top:8px">...and ${members.length - 50} more</p>` : ''}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderModuleList(modules) {
  // Already handled by pack layout click
}

// ── Utils ────────────────────────────────────────────────────────
function truncatePath(p, max) {
  if (!p) return '';
  const parts = p.split('/');
  const short = parts.slice(-2).join('/');
  return short.length > max ? short.slice(0, max - 1) + '\u2026' : short;
}

function esc(s) {
  if (!s) return '';
  const el = document.createElement('span');
  el.textContent = String(s);
  return el.innerHTML;
}
