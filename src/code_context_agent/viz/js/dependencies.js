/**
 * Dependencies view — interactive dependency chain explorer.
 */
import { state, NODE_COLORS, EDGE_COLORS, buildAdjacency, showTooltip, hideTooltip } from './state.js';

let depSvg, depG, depZoom;

export function renderDependencies() {
  if (!state.graph) return;

  setupDepSVG();
  bindDepControls();
}

function setupDepSVG() {
  const container = document.querySelector('.dep-container');
  depSvg = d3.select('#dep-svg');
  depSvg.selectAll('*').remove();

  depZoom = d3.zoom()
    .scaleExtent([0.2, 5])
    .on('zoom', (event) => depG.attr('transform', event.transform));

  depSvg.call(depZoom);
  depG = depSvg.append('g');

  // Arrow markers
  const defs = depSvg.append('defs');
  Object.entries(EDGE_COLORS).forEach(([type, color]) => {
    defs.append('marker')
      .attr('id', `dep-arrow-${type}`)
      .attr('viewBox', '0 -4 8 8')
      .attr('refX', 16)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-4L8,0L0,4')
      .attr('fill', color);
  });
}

function bindDepControls() {
  const searchInput = document.getElementById('dep-search');
  const acList = document.getElementById('dep-autocomplete');
  const depthRange = document.getElementById('dep-depth');
  const depthVal = document.getElementById('dep-depth-val');
  let acIndex = -1;

  depthRange.addEventListener('input', () => {
    depthVal.textContent = depthRange.value;
    if (searchInput.value) exploreDeps(searchInput.value);
  });

  // Autocomplete + search
  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim().toLowerCase();
    if (!q || q.length < 1) {
      closeAutocomplete();
      return;
    }
    showAutocomplete(q);
  });

  searchInput.addEventListener('keydown', (e) => {
    const items = acList.querySelectorAll('.autocomplete-item');
    if (!items.length) {
      if (e.key === 'Enter') {
        e.preventDefault();
        exploreDeps(searchInput.value);
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      acIndex = Math.min(acIndex + 1, items.length - 1);
      updateAcSelection(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      acIndex = Math.max(acIndex - 1, 0);
      updateAcSelection(items);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (acIndex >= 0 && items[acIndex]) {
        selectAcItem(items[acIndex].dataset.name);
      } else {
        exploreDeps(searchInput.value);
      }
    } else if (e.key === 'Escape') {
      closeAutocomplete();
    }
  });

  // Close on click outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.autocomplete-wrap')) closeAutocomplete();
  });

  function showAutocomplete(q) {
    if (!state.graph) return;
    const matches = state.graph.nodes
      .filter(n => n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q))
      .slice(0, 12);

    if (matches.length === 0) {
      closeAutocomplete();
      return;
    }

    acIndex = -1;
    acList.innerHTML = matches.map(n => {
      const color = NODE_COLORS[n.nodeType] || '#71717a';
      const highlighted = highlightMatch(esc(n.name), q);
      return `<li class="autocomplete-item" data-name="${esc(n.name)}" data-id="${esc(n.id)}">
        <span class="node-type-dot" style="background:${color}"></span>
        <span class="ac-name">${highlighted}</span>
        <span class="ac-type">${n.nodeType}</span>
      </li>`;
    }).join('');

    acList.classList.add('open');

    acList.querySelectorAll('.autocomplete-item').forEach(item => {
      item.addEventListener('click', () => selectAcItem(item.dataset.name));
      item.addEventListener('mouseenter', () => {
        acIndex = -1;
        acList.querySelectorAll('.autocomplete-item').forEach(i => i.classList.remove('selected'));
        item.classList.add('selected');
      });
    });
  }

  function selectAcItem(name) {
    searchInput.value = name;
    closeAutocomplete();
    exploreDeps(name);
  }

  function closeAutocomplete() {
    acList.classList.remove('open');
    acList.innerHTML = '';
    acIndex = -1;
  }

  function updateAcSelection(items) {
    items.forEach((item, i) => item.classList.toggle('selected', i === acIndex));
    if (acIndex >= 0 && items[acIndex]) {
      items[acIndex].scrollIntoView({ block: 'nearest' });
    }
  }

  function highlightMatch(text, query) {
    const idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) return text;
    return text.slice(0, idx) + '<mark>' + text.slice(idx, idx + query.length) + '</mark>' + text.slice(idx + query.length);
  }
}

function exploreDeps(query) {
  const q = query.toLowerCase();
  const rootNode = state.graph.nodes.find(n =>
    n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q)
  );

  if (!rootNode) {
    document.getElementById('dep-info').innerHTML = `<p class="text-muted">No node found matching "${esc(query)}"</p>`;
    return;
  }

  const direction = document.querySelector('input[name="dep-dir"]:checked').value;
  const maxDepth = parseInt(document.getElementById('dep-depth').value, 10);

  const { nodes, edges } = getDepChain(rootNode.id, direction, maxDepth);
  renderDepTree(rootNode, nodes, edges, direction);
  renderDepInfo(rootNode, nodes, edges, direction);
}

function getDepChain(rootId, direction, maxDepth) {
  const { outgoing, incoming } = buildAdjacency();
  const visited = new Map(); // id -> distance
  const edges = [];
  const queue = [[rootId, 0]];
  visited.set(rootId, 0);

  while (queue.length > 0) {
    const [nodeId, dist] = queue.shift();
    if (dist >= maxDepth) continue;

    const neighbors = direction === 'outgoing'
      ? (outgoing.get(nodeId) || [])
      : (incoming.get(nodeId) || []);

    for (const n of neighbors) {
      const targetId = direction === 'outgoing' ? n.target : n.source;
      // Only follow calls, imports, inherits edges
      if (!['calls', 'imports', 'inherits', 'implements'].includes(n.edge.edgeType)) continue;

      edges.push({
        source: direction === 'outgoing' ? nodeId : targetId,
        target: direction === 'outgoing' ? targetId : nodeId,
        edgeType: n.edge.edgeType,
      });

      if (!visited.has(targetId)) {
        visited.set(targetId, dist + 1);
        queue.push([targetId, dist + 1]);
      }
    }
  }

  const nodes = [];
  for (const [id, dist] of visited) {
    const n = state.nodeIndex.get(id);
    if (n) nodes.push({ ...n, distance: dist });
  }

  return { nodes, edges };
}

function renderDepTree(rootNode, nodes, edges, direction) {
  depG.selectAll('*').remove();

  if (nodes.length === 0) return;

  const container = document.querySelector('.dep-container');
  const w = container.clientWidth - 300;
  const h = container.clientHeight;

  // Tree layout: group by distance
  const levels = new Map();
  for (const n of nodes) {
    if (!levels.has(n.distance)) levels.set(n.distance, []);
    levels.get(n.distance).push(n);
  }

  const maxLevel = Math.max(...levels.keys());
  const levelSpacing = Math.min(200, (w - 100) / (maxLevel + 1));

  // Position nodes
  const positions = new Map();
  for (const [level, levelNodes] of levels) {
    const ySpacing = Math.min(40, (h - 40) / (levelNodes.length + 1));
    const yOffset = (h - ySpacing * levelNodes.length) / 2;
    levelNodes.forEach((n, i) => {
      positions.set(n.id, {
        x: 60 + level * levelSpacing,
        y: yOffset + i * ySpacing + ySpacing / 2,
      });
    });
  }

  // Draw edges
  for (const edge of edges) {
    const from = positions.get(edge.source);
    const to = positions.get(edge.target);
    if (!from || !to) continue;

    const color = EDGE_COLORS[edge.edgeType] || '#6a6a86';

    depG.append('path')
      .attr('d', `M${from.x},${from.y} C${from.x + levelSpacing * 0.4},${from.y} ${to.x - levelSpacing * 0.4},${to.y} ${to.x},${to.y}`)
      .attr('fill', 'none')
      .attr('stroke', color)
      .attr('stroke-width', 2)
      .attr('stroke-opacity', 0.7)
      .attr('marker-end', `url(#dep-arrow-${edge.edgeType})`);
  }

  // Draw nodes
  for (const node of nodes) {
    const pos = positions.get(node.id);
    if (!pos) continue;

    const color = NODE_COLORS[node.nodeType] || '#6a6a86';
    const isRoot = node.id === rootNode.id;
    const r = isRoot ? 10 : 6;

    const nodeG = depG.append('g')
      .attr('transform', `translate(${pos.x},${pos.y})`)
      .style('cursor', 'pointer')
      .on('mouseover', (event) => {
        showTooltip(event,
          `<div class="tt-label">${esc(node.name)}</div>` +
          `<span class="tt-type" style="background:${color}20;color:${color}">${node.nodeType}</span>` +
          (node.filePath ? `<div class="tt-mono tt-muted">${esc(node.filePath.split('/').slice(-3).join('/'))}</div>` : '') +
          `<div class="tt-muted" style="margin-top:2px">Depth: ${node.distance}</div>`
        );
      })
      .on('mouseout', () => hideTooltip());

    nodeG.append('circle')
      .attr('r', r)
      .attr('fill', color)
      .attr('stroke', isRoot ? 'var(--accent-hover)' : 'var(--bg-root)')
      .attr('stroke-width', isRoot ? 3 : 2);

    nodeG.append('text')
      .attr('x', r + 6)
      .attr('y', 4)
      .attr('fill', isRoot ? 'var(--text-primary)' : 'var(--text-secondary)')
      .attr('font-size', isRoot ? '14px' : '12px')
      .attr('font-weight', isRoot ? '700' : '400')
      .attr('font-family', 'var(--font-mono)')
      .text(truncate(node.name, 30));
  }

  // Fit to view
  const allX = [...positions.values()].map(p => p.x);
  const allY = [...positions.values()].map(p => p.y);
  const minX = Math.min(...allX) - 40;
  const minY = Math.min(...allY) - 40;
  const maxX = Math.max(...allX) + 200;
  const maxY = Math.max(...allY) + 40;
  const dw = maxX - minX;
  const dh = maxY - minY;
  const scale = Math.min(0.95, Math.min(w / dw, h / dh));
  const tx = (w - dw * scale) / 2 - minX * scale;
  const ty = (h - dh * scale) / 2 - minY * scale;

  depSvg.transition().duration(500).call(
    depZoom.transform,
    d3.zoomIdentity.translate(tx, ty).scale(scale)
  );
}

function renderDepInfo(rootNode, nodes, edges, direction) {
  const container = document.getElementById('dep-info');
  const color = NODE_COLORS[rootNode.nodeType] || '#6a6a86';

  // Group by distance
  const levels = new Map();
  for (const n of nodes) {
    if (n.id === rootNode.id) continue;
    if (!levels.has(n.distance)) levels.set(n.distance, []);
    levels.get(n.distance).push(n);
  }

  container.innerHTML = `
    <div style="margin-bottom:16px">
      <div style="font-family:var(--font-mono);font-weight:700;font-size:var(--text-base);color:var(--text-primary);margin-bottom:4px">${esc(rootNode.name)}</div>
      <span class="detail-type" style="background:${color}20;color:${color}">${rootNode.nodeType}</span>
      <div style="font-size:var(--text-xs);color:var(--text-muted);margin-top:8px">
        ${direction === 'outgoing' ? 'Depends on' : 'Depended on by'} <strong>${nodes.length - 1}</strong> nodes across <strong>${levels.size}</strong> levels
      </div>
    </div>
    ${Array.from(levels.entries()).sort(([a], [b]) => a - b).map(([dist, levelNodes]) => `
      <div style="margin-bottom:12px">
        <h4 style="font-size:var(--text-xs);text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:6px;font-weight:600">
          ${direction === 'outgoing' ? 'Depth' : 'Level'} ${dist} (${levelNodes.length})
        </h4>
        ${levelNodes.slice(0, 20).map(n => `
          <div style="display:flex;align-items:center;gap:6px;padding:3px 0;font-size:var(--text-xs)">
            <span class="node-type-dot" style="background:${NODE_COLORS[n.nodeType] || '#6a6a86'}"></span>
            <span style="font-family:var(--font-mono);color:var(--text-primary)">${esc(n.name)}</span>
          </div>
        `).join('')}
        ${levelNodes.length > 20 ? `<p class="text-muted">...and ${levelNodes.length - 20} more</p>` : ''}
      </div>
    `).join('')}
  `;
}

// ── Utils ────────────────────────────────────────────────────────
function truncate(s, max) {
  return s && s.length > max ? s.slice(0, max - 1) + '\u2026' : s;
}

function esc(s) {
  if (!s) return '';
  const el = document.createElement('span');
  el.textContent = String(s);
  return el.innerHTML;
}
