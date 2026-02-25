/**
 * Network Graph view — force-directed D3 visualization.
 */
import { state, NODE_COLORS, EDGE_COLORS, buildAdjacency, showTooltip, hideTooltip } from './state.js';

let simulation = null;
let svg, g, linkGroup, nodeGroup, labelGroup;
let zoom;
let activeFilters = { nodeTypes: new Set(), edgeTypes: new Set() };
let selectedNodeId = null;

// ── Initialization ───────────────────────────────────────────────
const MAX_NODES_FOR_LABELS = 500;
const MAX_NODES_WARNING = 2000;

export function initGraph() {
  if (!state.graph) return;

  // Performance warning for large graphs
  if (state.graph.nodes.length > MAX_NODES_WARNING) {
    const msg = document.createElement('div');
    msg.style.cssText = 'position:absolute;top:12px;left:50%;transform:translateX(-50%);z-index:10;background:var(--bg-elevated);border:1px solid var(--severity-medium);border-radius:6px;padding:8px 16px;font-size:12px;color:var(--severity-medium);';
    msg.textContent = `Large graph (${state.graph.nodes.length} nodes). Consider filtering node types for better performance.`;
    document.querySelector('.graph-container').appendChild(msg);
    setTimeout(() => msg.remove(), 6000);
  }

  buildFilterChips();
  buildLegend();
  setupSVG();
  runSimulation();
  bindControls();
}

export function destroyGraph() {
  if (simulation) { simulation.stop(); simulation = null; }
}

// ── Filter Chips ─────────────────────────────────────────────────
function buildFilterChips() {
  const nodeContainer = document.getElementById('node-type-filters');
  const edgeContainer = document.getElementById('edge-type-filters');

  // Initialize all as active
  activeFilters.nodeTypes = new Set(Object.keys(state.nodeTypes));
  activeFilters.edgeTypes = new Set(Object.keys(state.edgeTypes));

  nodeContainer.innerHTML = Object.keys(state.nodeTypes).map(t => `
    <button class="filter-chip active" data-type="${t}" style="--chip-color:${NODE_COLORS[t] || '#6a6a86'}">
      ${t} <small>(${state.nodeTypes[t]})</small>
    </button>
  `).join('');

  edgeContainer.innerHTML = Object.keys(state.edgeTypes).map(t => `
    <button class="filter-chip active" data-type="${t}" style="--chip-color:${EDGE_COLORS[t] || '#6a6a86'}">
      ${t} <small>(${state.edgeTypes[t]})</small>
    </button>
  `).join('');

  nodeContainer.addEventListener('click', e => {
    const chip = e.target.closest('.filter-chip');
    if (!chip) return;
    const type = chip.dataset.type;
    chip.classList.toggle('active');
    if (activeFilters.nodeTypes.has(type)) activeFilters.nodeTypes.delete(type);
    else activeFilters.nodeTypes.add(type);
    applyFilters();
  });

  edgeContainer.addEventListener('click', e => {
    const chip = e.target.closest('.filter-chip');
    if (!chip) return;
    const type = chip.dataset.type;
    chip.classList.toggle('active');
    if (activeFilters.edgeTypes.has(type)) activeFilters.edgeTypes.delete(type);
    else activeFilters.edgeTypes.add(type);
    applyFilters();
  });
}

function buildLegend() {
  const legend = document.getElementById('graph-legend');
  legend.innerHTML = Object.entries(NODE_COLORS).map(([type, color]) =>
    `<span class="legend-item"><span class="legend-dot" style="background:${color}"></span>${type}</span>`
  ).join('');
}

// ── SVG Setup ────────────────────────────────────────────────────
function setupSVG() {
  const container = document.querySelector('.graph-container');
  svg = d3.select('#graph-svg');
  svg.selectAll('*').remove();

  const w = container.clientWidth;
  const h = container.clientHeight;

  // Defs for arrow markers
  const defs = svg.append('defs');
  Object.entries(EDGE_COLORS).forEach(([type, color]) => {
    defs.append('marker')
      .attr('id', `arrow-${type}`)
      .attr('viewBox', '0 -3 6 6')
      .attr('refX', 12)
      .attr('refY', 0)
      .attr('markerWidth', 5)
      .attr('markerHeight', 5)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-3L6,0L0,3')
      .attr('fill', color);
  });

  // Zoom behavior
  zoom = d3.zoom()
    .scaleExtent([0.1, 8])
    .on('zoom', (event) => {
      g.attr('transform', event.transform);
      updateMinimap(event.transform, w, h);
    });

  svg.call(zoom);

  g = svg.append('g');
  linkGroup = g.append('g').attr('class', 'links');
  nodeGroup = g.append('g').attr('class', 'nodes');
  labelGroup = g.append('g').attr('class', 'labels');
}

// ── Simulation ───────────────────────────────────────────────────
function runSimulation() {
  const { nodes, links } = state.graph;
  const container = document.querySelector('.graph-container');
  const w = container.clientWidth;
  const h = container.clientHeight;

  // Limit link distance by edge type
  const linkDistance = (d) => {
    const type = d.edgeType;
    if (type === 'contains') return 30;
    if (type === 'inherits' || type === 'implements') return 60;
    if (type === 'calls') return 80;
    return 100;
  };

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links)
      .id(d => d.id)
      .distance(linkDistance)
      .strength(0.3))
    .force('charge', d3.forceManyBody()
      .strength(d => {
        const degree = getNodeDegree(d);
        return -Math.max(40, degree * 8);
      })
      .distanceMax(400))
    .force('center', d3.forceCenter(w / 2, h / 2).strength(0.05))
    .force('collision', d3.forceCollide().radius(d => nodeRadius(d) + 3))
    .force('x', d3.forceX(w / 2).strength(0.02))
    .force('y', d3.forceY(h / 2).strength(0.02))
    .alphaDecay(0.02)
    .velocityDecay(0.4);

  // Draw links
  const link = linkGroup.selectAll('line')
    .data(links)
    .enter()
    .append('line')
    .attr('class', 'graph-link')
    .attr('stroke', d => EDGE_COLORS[d.edgeType] || '#6a6a86')
    .attr('stroke-width', d => {
      if (d.edgeType === 'contains') return 0.5;
      return Math.max(1, Math.min(3, d.weight));
    })
    .attr('stroke-dasharray', d => {
      if (d.edgeType === 'imports') return '4,3';
      if (d.edgeType === 'references') return '2,2';
      if (d.edgeType === 'cochanges') return '6,3';
      return null;
    })
    .attr('marker-end', d => d.edgeType !== 'contains' ? `url(#arrow-${d.edgeType})` : null);

  // Draw nodes
  const node = nodeGroup.selectAll('g')
    .data(nodes)
    .enter()
    .append('g')
    .attr('class', 'graph-node')
    .call(d3.drag()
      .on('start', dragStart)
      .on('drag', dragging)
      .on('end', dragEnd));

  node.append('circle')
    .attr('r', d => nodeRadius(d))
    .attr('fill', d => NODE_COLORS[d.nodeType] || '#6a6a86');

  // Labels (only for larger/important nodes; hidden entirely for very large graphs)
  const showLabels = nodes.length <= MAX_NODES_FOR_LABELS;
  const minDegreeForLabel = nodes.length > 200 ? 6 : nodes.length > 100 ? 4 : 3;

  const label = labelGroup.selectAll('text')
    .data(nodes)
    .enter()
    .append('text')
    .attr('class', 'graph-node-label')
    .attr('text-anchor', 'middle')
    .attr('dy', d => nodeRadius(d) + 12)
    .attr('fill', 'var(--text-muted)')
    .attr('font-size', '9px')
    .attr('pointer-events', 'none')
    .text(d => truncate(d.name, 20))
    .style('display', d => showLabels && getNodeDegree(d) > minDegreeForLabel ? null : 'none');

  // Tooltip on hover
  node.on('mouseover', function(event, d) {
    const degree = getNodeDegree(d);
    const color = NODE_COLORS[d.nodeType] || '#6a6a86';
    const { outgoing: adjOut, incoming: adjIn } = buildAdjacency();
    const inDeg = (adjIn.get(d.id) || []).length;
    const outDeg = (adjOut.get(d.id) || []).length;
    showTooltip(event,
      `<div class="tt-label">${esc(d.name)}</div>` +
      `<span class="tt-type" style="background:${color}20;color:${color}">${d.nodeType}</span>` +
      (d.filePath ? `<div class="tt-mono tt-muted">${esc(shortPath(d.filePath))}${d.lineStart ? ':' + d.lineStart : ''}</div>` : '') +
      `<div class="tt-row" style="margin-top:3px"><span class="tt-muted">Degree ${degree}</span> &middot; ${inDeg} in &middot; ${outDeg} out</div>`
    );
    if (selectedNodeId && selectedNodeId !== d.id) return;
    highlightNeighbors(d.id);
    d3.select(this).classed('highlight', true);
  }).on('mouseout', function() {
    hideTooltip();
    if (selectedNodeId) return;
    clearHighlights();
  }).on('click', function(event, d) {
    event.stopPropagation();
    hideTooltip();
    selectNode(d);
  });

  // Edge tooltip
  link.on('mouseover', function(event, d) {
    const sName = nameFromId(typeof d.source === 'object' ? d.source.id : d.source);
    const tName = nameFromId(typeof d.target === 'object' ? d.target.id : d.target);
    const color = EDGE_COLORS[d.edgeType] || '#6a6a86';
    showTooltip(event,
      `<span class="tt-type" style="background:${color}20;color:${color}">${d.edgeType}</span>` +
      `<div class="tt-mono" style="margin-top:3px">${esc(sName)} → ${esc(tName)}</div>` +
      (d.weight > 1 ? `<div class="tt-muted">weight: ${d.weight}</div>` : '')
    );
    d3.select(this).attr('stroke-opacity', 0.9).attr('stroke-width', 3);
  }).on('mouseout', function(event, d) {
    hideTooltip();
    const w = d.edgeType === 'contains' ? 0.5 : Math.max(1, Math.min(3, d.weight));
    d3.select(this).attr('stroke-opacity', 0.4).attr('stroke-width', w);
  });

  svg.on('click', () => {
    deselectNode();
  });

  // Tick
  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);

    node.attr('transform', d => `translate(${d.x},${d.y})`);
    label.attr('x', d => d.x).attr('y', d => d.y);
  });

  // Initial zoom to fit
  simulation.on('end', () => zoomToFit());
  setTimeout(() => zoomToFit(), 2000);
}

// ── Node sizing ──────────────────────────────────────────────────
const _degreeCache = new Map();

function getNodeDegree(d) {
  if (_degreeCache.has(d.id)) return _degreeCache.get(d.id);
  if (!state.graph) return 0;
  let count = 0;
  for (const l of state.graph.links) {
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    if (sid === d.id || tid === d.id) count++;
  }
  _degreeCache.set(d.id, count);
  return count;
}

function nodeRadius(d) {
  const degree = getNodeDegree(d);
  const base = d.nodeType === 'file' ? 6 : d.nodeType === 'class' ? 7 : 5;
  return Math.max(base, Math.min(20, base + Math.sqrt(degree) * 1.5));
}

// ── Drag ─────────────────────────────────────────────────────────
function dragStart(event, d) {
  if (!event.active) simulation.alphaTarget(0.1).restart();
  d.fx = d.x;
  d.fy = d.y;
}

function dragging(event, d) {
  d.fx = event.x;
  d.fy = event.y;
}

function dragEnd(event, d) {
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null;
  d.fy = null;
}

// ── Selection & Highlighting ─────────────────────────────────────
function highlightNeighbors(nodeId) {
  const neighborIds = new Set([nodeId]);
  const links = state.graph.links;

  for (const l of links) {
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    if (sid === nodeId) neighborIds.add(tid);
    if (tid === nodeId) neighborIds.add(sid);
  }

  nodeGroup.selectAll('.graph-node')
    .classed('dimmed', d => !neighborIds.has(d.id));

  linkGroup.selectAll('.graph-link')
    .classed('dimmed', d => {
      const sid = typeof d.source === 'object' ? d.source.id : d.source;
      const tid = typeof d.target === 'object' ? d.target.id : d.target;
      return sid !== nodeId && tid !== nodeId;
    })
    .classed('highlight', d => {
      const sid = typeof d.source === 'object' ? d.source.id : d.source;
      const tid = typeof d.target === 'object' ? d.target.id : d.target;
      return sid === nodeId || tid === nodeId;
    });

  labelGroup.selectAll('text')
    .style('display', d => neighborIds.has(d.id) ? null : 'none');
}

function clearHighlights() {
  nodeGroup.selectAll('.graph-node').classed('dimmed', false);
  linkGroup.selectAll('.graph-link').classed('dimmed', false).classed('highlight', false);
  labelGroup.selectAll('text').style('display', d => getNodeDegree(d) > 3 ? null : 'none');
}

function selectNode(d) {
  selectedNodeId = d.id;
  highlightNeighbors(d.id);
  showDetailPanel(d);
}

function deselectNode() {
  selectedNodeId = null;
  clearHighlights();
  document.getElementById('graph-detail').style.display = 'none';
}

// ── Detail Panel ─────────────────────────────────────────────────
function showDetailPanel(d) {
  const panel = document.getElementById('graph-detail');
  const content = document.getElementById('detail-content');
  panel.style.display = 'block';

  const { outgoing, incoming } = buildAdjacency();
  const out = (outgoing.get(d.id) || []);
  const inc = (incoming.get(d.id) || []);

  const color = NODE_COLORS[d.nodeType] || '#6a6a86';

  content.innerHTML = `
    <div class="detail-title">${esc(d.name)}</div>
    <span class="detail-type" style="background:${color}20;color:${color}">${d.nodeType}</span>
    <div class="detail-section">
      <h4>Location</h4>
      <p style="font-family:var(--font-mono);font-size:var(--text-xs);color:var(--text-secondary);word-break:break-all">
        ${esc(shortPath(d.filePath))}:${d.lineStart}
      </p>
    </div>
    ${d.metadata?.category ? `<div class="detail-section"><h4>Category</h4><span class="category-badge" data-category="${esc(d.metadata.category)}">${esc(d.metadata.category)}</span></div>` : ''}
    <div class="detail-section">
      <h4>Connections</h4>
      <p style="font-size:var(--text-xs);color:var(--text-muted)">${inc.length} incoming, ${out.length} outgoing</p>
    </div>
    ${out.length > 0 ? `
      <div class="detail-section">
        <h4>Calls / Depends On (${out.length})</h4>
        <ul class="detail-list">
          ${out.slice(0, 15).map(e => `<li data-node="${esc(e.target)}">${esc(nameFromId(e.target))} <small style="color:var(--text-muted)">${e.edge.edgeType}</small></li>`).join('')}
          ${out.length > 15 ? `<li class="text-muted">...and ${out.length - 15} more</li>` : ''}
        </ul>
      </div>
    ` : ''}
    ${inc.length > 0 ? `
      <div class="detail-section">
        <h4>Called By / Depended On (${inc.length})</h4>
        <ul class="detail-list">
          ${inc.slice(0, 15).map(e => `<li data-node="${esc(e.source)}">${esc(nameFromId(e.source))} <small style="color:var(--text-muted)">${e.edge.edgeType}</small></li>`).join('')}
          ${inc.length > 15 ? `<li class="text-muted">...and ${inc.length - 15} more</li>` : ''}
        </ul>
      </div>
    ` : ''}
  `;

  // Click on list items to navigate
  content.querySelectorAll('.detail-list li[data-node]').forEach(li => {
    li.addEventListener('click', () => {
      const targetId = li.dataset.node;
      const targetNode = state.graph.nodes.find(n => n.id === targetId);
      if (targetNode) selectNode(targetNode);
    });
  });
}

// ── Filtering ────────────────────────────────────────────────────
function applyFilters() {
  nodeGroup.selectAll('.graph-node')
    .style('display', d => activeFilters.nodeTypes.has(d.nodeType) ? null : 'none');

  linkGroup.selectAll('.graph-link')
    .style('display', d => {
      if (!activeFilters.edgeTypes.has(d.edgeType)) return 'none';
      const sNode = typeof d.source === 'object' ? d.source : state.nodeIndex.get(d.source);
      const tNode = typeof d.target === 'object' ? d.target : state.nodeIndex.get(d.target);
      if (sNode && !activeFilters.nodeTypes.has(sNode.nodeType)) return 'none';
      if (tNode && !activeFilters.nodeTypes.has(tNode.nodeType)) return 'none';
      return null;
    });

  labelGroup.selectAll('text')
    .style('display', d => activeFilters.nodeTypes.has(d.nodeType) && getNodeDegree(d) > 3 ? null : 'none');
}

// ── Search ───────────────────────────────────────────────────────
function handleSearch(query) {
  if (!query) { clearHighlights(); return; }
  const q = query.toLowerCase();
  const match = state.graph.nodes.find(n =>
    n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q)
  );
  if (match) {
    selectNode(match);
    // Pan to node
    const container = document.querySelector('.graph-container');
    const w = container.clientWidth;
    const h = container.clientHeight;
    const t = d3.zoomIdentity.translate(w / 2 - match.x, h / 2 - match.y);
    svg.transition().duration(500).call(zoom.transform, t);
  }
}

// ── Zoom Controls ────────────────────────────────────────────────
function zoomToFit() {
  if (!state.graph || state.graph.nodes.length === 0) return;
  const container = document.querySelector('.graph-container');
  const w = container.clientWidth;
  const h = container.clientHeight;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of state.graph.nodes) {
    if (n.x < minX) minX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.x > maxX) maxX = n.x;
    if (n.y > maxY) maxY = n.y;
  }

  const dx = maxX - minX + 80;
  const dy = maxY - minY + 80;
  const scale = Math.min(0.9, Math.min(w / dx, h / dy));
  const tx = (w - dx * scale) / 2 - minX * scale + 40 * scale;
  const ty = (h - dy * scale) / 2 - minY * scale + 40 * scale;

  svg.transition().duration(750).call(
    zoom.transform,
    d3.zoomIdentity.translate(tx, ty).scale(scale)
  );
}

function bindControls() {
  document.getElementById('btn-zoom-in').addEventListener('click', () => {
    svg.transition().duration(300).call(zoom.scaleBy, 1.5);
  });
  document.getElementById('btn-zoom-out').addEventListener('click', () => {
    svg.transition().duration(300).call(zoom.scaleBy, 0.67);
  });
  document.getElementById('btn-zoom-fit').addEventListener('click', zoomToFit);
  document.getElementById('detail-close').addEventListener('click', deselectNode);

  const searchInput = document.getElementById('graph-search');
  let searchTimeout;
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => handleSearch(searchInput.value), 200);
  });

  // Layout switcher
  document.getElementById('graph-layout').addEventListener('change', (e) => {
    const layout = e.target.value;
    applyLayout(layout);
  });

  document.getElementById('btn-graph-screenshot').addEventListener('click', () => {
    const svgData = new XMLSerializer().serializeToString(document.getElementById('graph-svg'));
    const blob = new Blob([svgData], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'code-graph.svg';
    a.click();
    URL.revokeObjectURL(url);
  });
}

// ── Minimap ──────────────────────────────────────────────────────
function updateMinimap(transform, fullW, fullH) {
  const minimapSvg = d3.select('#minimap-svg');
  minimapSvg.selectAll('*').remove();

  if (!state.graph || state.graph.nodes.length === 0) return;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of state.graph.nodes) {
    if (n.x < minX) minX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.x > maxX) maxX = n.x;
    if (n.y > maxY) maxY = n.y;
  }

  const mw = 160, mh = 120;
  const dx = maxX - minX || 1;
  const dy = maxY - minY || 1;
  const scale = Math.min(mw / dx, mh / dy) * 0.85;
  const ox = (mw - dx * scale) / 2 - minX * scale;
  const oy = (mh - dy * scale) / 2 - minY * scale;

  // Draw nodes as tiny dots
  const mg = minimapSvg.append('g').attr('transform', `translate(${ox},${oy}) scale(${scale})`);
  mg.selectAll('circle')
    .data(state.graph.nodes)
    .enter()
    .append('circle')
    .attr('cx', d => d.x)
    .attr('cy', d => d.y)
    .attr('r', 2 / scale)
    .attr('fill', d => NODE_COLORS[d.nodeType] || '#6a6a86')
    .attr('opacity', 0.6);

  // Viewport rectangle
  const vx = (-transform.x / transform.k) * scale + ox;
  const vy = (-transform.y / transform.k) * scale + oy;
  const vw = (fullW / transform.k) * scale;
  const vh = (fullH / transform.k) * scale;

  minimapSvg.append('rect')
    .attr('class', 'minimap-viewport')
    .attr('x', vx).attr('y', vy)
    .attr('width', vw).attr('height', vh);
}

// ── Layout Modes ─────────────────────────────────────────────────
function applyLayout(mode) {
  if (!state.graph || !simulation) return;
  const container = document.querySelector('.graph-container');
  const w = container.clientWidth;
  const h = container.clientHeight;
  const cx = w / 2, cy = h / 2;

  if (mode === 'force') {
    // Re-enable force simulation
    simulation
      .force('center', d3.forceCenter(cx, cy).strength(0.05))
      .force('x', d3.forceX(cx).strength(0.02))
      .force('y', d3.forceY(cy).strength(0.02))
      .alpha(0.5).restart();
    return;
  }

  // Stop simulation for manual positioning
  simulation.stop();

  if (mode === 'radial') {
    // Arrange nodes in concentric rings by degree
    const nodes = [...state.graph.nodes].sort((a, b) => getNodeDegree(b) - getNodeDegree(a));
    const rings = 5;
    const nodesPerRing = Math.ceil(nodes.length / rings);

    nodes.forEach((n, i) => {
      const ring = Math.floor(i / nodesPerRing);
      const posInRing = i - ring * nodesPerRing;
      const totalInRing = Math.min(nodesPerRing, nodes.length - ring * nodesPerRing);
      const angle = (2 * Math.PI * posInRing) / totalInRing - Math.PI / 2;
      const radius = 80 + ring * 100;
      n.x = cx + radius * Math.cos(angle);
      n.y = cy + radius * Math.sin(angle);
    });
  } else if (mode === 'hierarchy') {
    // Group by file path depth, arrange in columns
    const byFile = new Map();
    for (const n of state.graph.nodes) {
      const parts = n.filePath.split('/').filter(Boolean);
      const dir = parts.slice(0, Math.min(3, parts.length - 1)).join('/') || 'root';
      if (!byFile.has(dir)) byFile.set(dir, []);
      byFile.get(dir).push(n);
    }

    const groups = Array.from(byFile.entries()).sort((a, b) => b[1].length - a[1].length);
    const colWidth = Math.min(180, (w - 100) / groups.length);

    groups.forEach(([, members], gi) => {
      const x = 60 + gi * colWidth;
      members.forEach((n, ni) => {
        n.x = x;
        n.y = 40 + ni * 30;
      });
    });
  }

  // Update positions immediately
  simulation.alpha(0); // prevent restart
  nodeGroup.selectAll('.graph-node').attr('transform', d => `translate(${d.x},${d.y})`);
  linkGroup.selectAll('.graph-link')
    .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
  labelGroup.selectAll('text').attr('x', d => d.x).attr('y', d => d.y);

  zoomToFit();
}

// ── Utils ────────────────────────────────────────────────────────
function truncate(s, maxLen) {
  return s && s.length > maxLen ? s.slice(0, maxLen - 1) + '\u2026' : s;
}

function shortPath(p) {
  if (!p) return '';
  const parts = p.split('/');
  return parts.slice(-3).join('/');
}

function nameFromId(id) {
  const n = state.nodeIndex.get(id);
  return n ? n.name : id.split(':').pop() || id;
}

function esc(s) {
  if (!s) return '';
  const el = document.createElement('span');
  el.textContent = String(s);
  return el.innerHTML;
}
