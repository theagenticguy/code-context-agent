// graph.js — D3 force-directed graph explorer view
// The most complex view: interactive node/edge visualization with filtering,
// search, zoom/pan, drag, detail panel, and performance throttling.

import { store } from '../store.js';
import { filterChips, attachFilterListeners } from '../components/filter-chips.js';
import { searchBar, attachSearchListeners } from '../components/search-bar.js';
import { showTooltip, hideTooltip } from '../components/tooltip.js';
import { NODE_COLORS, EDGE_COLORS, nodeColor, edgeColor, NODE_TYPE_LABELS } from '../colors.js';
import { filterGraph, shortPath } from '../graph-utils.js';
import { escapeHtml, safeHtml, rawHtml, setHTML } from '../escape.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_NODE_LIMIT = 500;
const MAX_TICKS = 300;
const TOP_LABEL_COUNT = 30;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Compute degree for each node in a graph. Returns a Map<nodeId, { in, out, total }>.
 * @param {object} graph
 * @returns {Map<string, {in: number, out: number, total: number}>}
 */
function computeDegrees(graph) {
  const deg = new Map();
  for (const n of graph.nodes) {
    deg.set(n.id, { in: 0, out: 0, total: 0 });
  }
  for (const l of graph.links) {
    const src = typeof l.source === 'object' ? l.source.id : l.source;
    const tgt = typeof l.target === 'object' ? l.target.id : l.target;
    if (deg.has(src)) {
      deg.get(src).out++;
      deg.get(src).total++;
    }
    if (deg.has(tgt)) {
      deg.get(tgt).in++;
      deg.get(tgt).total++;
    }
  }
  return deg;
}

/**
 * Take the top N nodes by degree from a graph. Returns a new graph object.
 * @param {object} graph
 * @param {number} limit
 * @returns {{ graph: object, truncated: boolean, totalNodes: number }}
 */
function limitByDegree(graph, limit) {
  if (graph.nodes.length <= limit) {
    return { graph, truncated: false, totalNodes: graph.nodes.length };
  }

  const degrees = computeDegrees(graph);
  const sorted = [...graph.nodes].sort(
    (a, b) => (degrees.get(b.id)?.total || 0) - (degrees.get(a.id)?.total || 0)
  );
  const kept = sorted.slice(0, limit);
  const keptIds = new Set(kept.map((n) => n.id));
  const keptLinks = graph.links.filter((l) => {
    const src = typeof l.source === 'object' ? l.source.id : l.source;
    const tgt = typeof l.target === 'object' ? l.target.id : l.target;
    return keptIds.has(src) && keptIds.has(tgt);
  });

  return {
    graph: { ...graph, nodes: kept, links: keptLinks },
    truncated: true,
    totalNodes: sorted.length,
  };
}

/**
 * Compute node radius from degree using sqrt scale.
 * @param {number} degree
 * @param {number} maxDegree
 * @returns {number}
 */
function nodeRadius(degree, maxDegree) {
  if (maxDegree === 0) return 6;
  return 4 + 16 * Math.sqrt(degree / maxDegree);
}

// ---------------------------------------------------------------------------
// render
// ---------------------------------------------------------------------------

/**
 * Render the graph explorer view.
 * @param {HTMLElement} container
 * @param {import('../store.js').Store} _store
 * @returns {() => void} cleanup function
 */
export function render(container, _store) {
  const d3 = window.d3;
  const graph = store.get('graph');

  // -- Empty state -----------------------------------------------------------
  if (!graph || !graph.nodes || graph.nodes.length === 0) {
    setHTML(container, `
      <div class="view-enter h-full flex items-center justify-center bg-bg">
        <div class="text-center max-w-md px-6">
          <div class="text-5xl mb-4 opacity-60">&#x1F578;</div>
          <h2 class="font-heading text-xl mb-2 text-fg">No Graph Data</h2>
          <p class="text-sm text-fg/60 font-base">
            Load a <code class="text-xs bg-bg2 px-1 py-0.5 rounded-base border border-border/40">code_graph.json</code>
            file or connect to a server to explore the force-directed graph.
          </p>
          <a href="#/" class="inline-block mt-4 px-4 py-2 rounded-base border-2 border-border bg-main text-main-fg font-heading text-sm neo-pressable">
            Go to Home
          </a>
        </div>
      </div>`);
    return () => {};
  }

  // -- State -----------------------------------------------------------------
  const nodeTypes = Object.keys(store.get('nodeTypes') || {});
  const edgeTypes = Object.keys(store.get('edgeTypes') || {});
  let activeNodeTypes = new Set(nodeTypes);
  let activeEdgeTypes = new Set(edgeTypes);
  let searchQuery = '';
  let nodeLimit = DEFAULT_NODE_LIMIT;
  let selectedNode = null;
  let simulation = null;

  /** @type {AbortController} */
  const ac = new AbortController();
  const signal = ac.signal;

  // -- Build HTML ------------------------------------------------------------
  setHTML(container, safeHtml`
    <div class="view-enter h-full flex flex-col bg-bg overflow-hidden">

      <!-- Toolbar -->
      <div class="flex-shrink-0 border-b-2 border-border bg-bg2 px-4 py-3 space-y-2">
        <!-- Row 1: Search + Node limit + Reset zoom -->
        <div class="flex items-center gap-3 flex-wrap">
          <div id="graph-search" class="w-64">${rawHtml(searchBar({ placeholder: 'Search nodes...', onSearch: () => {} }))}</div>

          <div class="flex items-center gap-2 text-xs font-base text-fg/70">
            <label for="graph-node-limit">Node limit:</label>
            <input id="graph-node-limit" type="number" value="${nodeLimit}" min="10" max="10000" step="50"
              class="w-20 h-7 px-2 text-xs rounded-base border-2 border-border bg-bg text-fg font-base neo-focus" />
          </div>

          <button id="graph-reset-zoom"
            class="neo-pressable px-3 py-1 text-xs rounded-base border-2 border-border bg-bg2 font-heading">
            Reset zoom
          </button>

          <span id="graph-truncation-warning" class="text-xs text-fg/50 font-base ml-auto"></span>
        </div>

        <!-- Row 2: Node type chips -->
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-xs font-heading text-fg/50 w-14 flex-shrink-0">Nodes</span>
          <div id="graph-node-chips">
            ${rawHtml(filterChips({
              items: nodeTypes,
              activeSet: activeNodeTypes,
              colorMap: NODE_COLORS,
              onChange: () => {},
            }))}
          </div>
        </div>

        <!-- Row 3: Edge type chips -->
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-xs font-heading text-fg/50 w-14 flex-shrink-0">Edges</span>
          <div id="graph-edge-chips">
            ${rawHtml(filterChips({
              items: edgeTypes,
              activeSet: activeEdgeTypes,
              colorMap: EDGE_COLORS,
              onChange: () => {},
            }))}
          </div>
        </div>
      </div>

      <!-- Main area: SVG + optional detail panel -->
      <div class="flex flex-1 min-h-0">
        <!-- SVG canvas -->
        <div id="graph-canvas" class="flex-1 relative overflow-hidden bg-bg"></div>

        <!-- Detail panel (hidden by default) -->
        <div id="graph-detail-panel" class="hidden w-72 border-l-2 border-border bg-bg2 p-4 overflow-auto flex-shrink-0">
        </div>
      </div>
    </div>`);

  // -- References ------------------------------------------------------------
  const canvasEl = container.querySelector('#graph-canvas');
  const detailPanel = container.querySelector('#graph-detail-panel');
  const truncationWarning = container.querySelector('#graph-truncation-warning');
  const nodeLimitInput = container.querySelector('#graph-node-limit');
  const resetZoomBtn = container.querySelector('#graph-reset-zoom');

  // -- SVG setup -------------------------------------------------------------
  const width = canvasEl.clientWidth || 800;
  const height = canvasEl.clientHeight || 600;

  const svg = d3.select(canvasEl)
    .append('svg')
    .attr('width', '100%')
    .attr('height', '100%')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('preserveAspectRatio', 'xMidYMid meet');

  // Defs: arrow marker + animated dash pattern
  const defs = svg.append('defs');

  // CSS for animated dashes on 'calls' edges
  const style = svg.append('style');
  style.text(`
    .edge-calls {
      stroke-dasharray: 6 3;
      animation: dash-flow 0.8s linear infinite;
    }
    @keyframes dash-flow {
      to { stroke-dashoffset: -9; }
    }
  `);

  const g = svg.append('g');

  // Zoom behavior
  const zoom = d3.zoom()
    .scaleExtent([0.1, 8])
    .on('zoom', (event) => {
      g.attr('transform', event.transform);
    });
  svg.call(zoom);

  // -- Draw graph function ---------------------------------------------------

  /** Current data references for interaction handlers */
  let currentNodes = [];
  let currentLinks = [];
  let currentDegrees = new Map();
  let currentNodeMap = new Map();
  let linkSel = null;
  let nodeSel = null;
  let labelSel = null;

  /**
   * Filter, limit, and render the graph into the SVG.
   */
  function drawGraph() {
    // Stop any existing simulation
    if (simulation) {
      simulation.stop();
      simulation = null;
    }

    // Apply filters
    let filtered = filterGraph(graph, {
      nodeTypes: activeNodeTypes.size === nodeTypes.length ? undefined : activeNodeTypes,
      edgeTypes: activeEdgeTypes.size === edgeTypes.length ? undefined : activeEdgeTypes,
    });

    // Apply node limit
    const { graph: limited, truncated, totalNodes } = limitByDegree(filtered, nodeLimit);
    filtered = limited;

    // Update truncation warning
    if (truncated) {
      truncationWarning.textContent = `Showing ${nodeLimit} of ${totalNodes} nodes`;
    } else {
      truncationWarning.textContent = `${filtered.nodes.length} nodes, ${filtered.links.length} edges`;
    }

    // Deep-copy nodes and links for D3 mutation
    currentNodes = filtered.nodes.map((n) => ({ ...n }));
    currentLinks = filtered.links.map((l) => ({
      ...l,
      source: typeof l.source === 'object' ? l.source.id : l.source,
      target: typeof l.target === 'object' ? l.target.id : l.target,
    }));

    // Compute degrees on the filtered subgraph
    currentDegrees = computeDegrees({ nodes: currentNodes, links: currentLinks });
    currentNodeMap = new Map(currentNodes.map((n) => [n.id, n]));

    const maxDegree = Math.max(1, ...Array.from(currentDegrees.values()).map((d) => d.total));

    // Assign radius to each node
    for (const n of currentNodes) {
      n.r = nodeRadius(currentDegrees.get(n.id)?.total || 0, maxDegree);
    }

    // Identify top nodes for labels
    const sortedByDegree = [...currentNodes].sort(
      (a, b) => (currentDegrees.get(b.id)?.total || 0) - (currentDegrees.get(a.id)?.total || 0)
    );
    const topIds = new Set(sortedByDegree.slice(0, TOP_LABEL_COUNT).map((n) => n.id));

    // Clear previous drawing
    g.selectAll('*').remove();

    // Draw edges
    linkSel = g.append('g')
      .attr('class', 'links')
      .selectAll('line')
      .data(currentLinks)
      .join('line')
      .attr('stroke', (d) => edgeColor(d.edge_type))
      .attr('stroke-opacity', (d) => d.confidence ?? 0.6)
      .attr('stroke-width', (d) => Math.min(3, Math.max(1, d.weight || 1)))
      .attr('class', (d) => d.edge_type === 'calls' ? 'edge-calls' : '');

    // Draw nodes
    nodeSel = g.append('g')
      .attr('class', 'nodes')
      .selectAll('circle')
      .data(currentNodes)
      .join('circle')
      .attr('r', (d) => d.r)
      .attr('fill', (d) => nodeColor(d.node_type))
      .attr('stroke', 'var(--border)')
      .attr('stroke-width', 2)
      .attr('cursor', 'pointer');

    // Draw labels (only for top N by degree)
    labelSel = g.append('g')
      .attr('class', 'labels')
      .selectAll('text')
      .data(currentNodes.filter((n) => topIds.has(n.id)))
      .join('text')
      .text((d) => d.name)
      .attr('font-size', 10)
      .attr('font-family', 'inherit')
      .attr('font-weight', 500)
      .attr('fill', 'var(--foreground)')
      .attr('text-anchor', 'middle')
      .attr('dy', (d) => -d.r - 4)
      .attr('pointer-events', 'none')
      .attr('opacity', 0.85);

    // -- Simulation ----------------------------------------------------------
    const svgWidth = canvasEl.clientWidth || width;
    const svgHeight = canvasEl.clientHeight || height;

    simulation = d3.forceSimulation(currentNodes)
      .force('link', d3.forceLink(currentLinks).id((d) => d.id).distance(60))
      .force('charge', d3.forceManyBody().strength(-150))
      .force('center', d3.forceCenter(svgWidth / 2, svgHeight / 2))
      .force('collide', d3.forceCollide().radius((d) => d.r + 2));

    // Tick counter for performance: pause after MAX_TICKS
    let tickCount = 0;
    const useThrottle = currentNodes.length > 500;
    let lastTickTime = 0;

    simulation.on('tick', () => {
      tickCount++;

      // Throttle rendering for large graphs: skip frames to maintain responsiveness
      if (useThrottle) {
        const now = performance.now();
        if (now - lastTickTime < 32 && tickCount < MAX_TICKS) return; // ~30fps cap
        lastTickTime = now;
      }

      linkSel
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y);

      nodeSel
        .attr('cx', (d) => d.x)
        .attr('cy', (d) => d.y);

      labelSel
        .attr('x', (d) => d.x)
        .attr('y', (d) => d.y);

      // Stop simulation after MAX_TICKS to save CPU
      if (tickCount >= MAX_TICKS) {
        simulation.stop();
      }
    });

    // -- Drag ----------------------------------------------------------------
    const drag = d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });

    nodeSel.call(drag);

    // -- Hover tooltip -------------------------------------------------------
    nodeSel
      .on('mouseover', (event, d) => {
        const deg = currentDegrees.get(d.id) || { in: 0, out: 0, total: 0 };
        showTooltip(
          safeHtml`<div class="space-y-0.5">
            <div class="font-heading text-sm">${d.name}</div>
            <div class="text-xs" style="color:${rawHtml(nodeColor(d.node_type))}">${NODE_TYPE_LABELS[d.node_type] || d.node_type}</div>
            ${rawHtml(d.file_path ? `<div class="text-xs text-fg/60">${escapeHtml(shortPath(d.file_path))}</div>` : '')}
            <div class="text-xs text-fg/50">in:${deg.in} out:${deg.out} total:${deg.total}</div>
          </div>`,
          event.clientX,
          event.clientY
        );
      })
      .on('mouseout', () => {
        hideTooltip();
      });

    // -- Click: select node, show detail panel --------------------------------
    nodeSel.on('click', (event, d) => {
      event.stopPropagation();
      selectNode(d);
    });

    // -- Double-click: zoom to neighborhood ----------------------------------
    nodeSel.on('dblclick', (event, d) => {
      event.stopPropagation();
      event.preventDefault();
      zoomToNode(d);
    });

    // Click on SVG background: deselect
    svg.on('click', () => {
      deselectNode();
    });

    // Apply search highlighting if there is an active query
    applySearchHighlight();
  }

  // -- Node selection / detail panel -----------------------------------------

  function selectNode(d) {
    selectedNode = d;

    // Highlight the selected node
    nodeSel.attr('stroke-width', (n) => n.id === d.id ? 4 : 2);

    // Build incoming/outgoing edge lists
    const incoming = currentLinks.filter((l) => {
      const tgt = typeof l.target === 'object' ? l.target.id : l.target;
      return tgt === d.id;
    });
    const outgoing = currentLinks.filter((l) => {
      const src = typeof l.source === 'object' ? l.source.id : l.source;
      return src === d.id;
    });

    const edgeBadge = (type) =>
      `<span class="text-[10px] px-1 py-0.5 rounded-base border border-border/40" style="color:${edgeColor(type)}">${escapeHtml(type)}</span>`;

    const edgeListItem = (nodeId, edgeType) => {
      const n = currentNodeMap.get(nodeId);
      const name = n ? n.name : nodeId;
      return `<li class="flex items-center gap-1.5 text-xs text-fg/70 truncate-line" title="${escapeHtml(name)}">${edgeBadge(edgeType)} ${escapeHtml(name)}</li>`;
    };

    const incomingHtml = incoming.map((l) => {
      const src = typeof l.source === 'object' ? l.source.id : l.source;
      return edgeListItem(src, l.edge_type);
    }).join('');

    const outgoingHtml = outgoing.map((l) => {
      const tgt = typeof l.target === 'object' ? l.target.id : l.target;
      return edgeListItem(tgt, l.edge_type);
    }).join('');

    const lineRange = (d.line_start || d.line_end)
      ? `${d.line_start}-${d.line_end}`
      : '';

    detailPanel.classList.remove('hidden');
    setHTML(detailPanel, safeHtml`
      <div class="space-y-3">
        <div>
          <button id="graph-detail-close" class="float-right text-xs text-fg/40 hover:text-fg cursor-pointer p-1" title="Close">&times;</button>
          <h3 class="font-heading text-sm text-fg leading-tight pr-6">${d.name}</h3>
          <span class="inline-block mt-1 text-xs px-1.5 py-0.5 rounded-base border border-border" style="color:${rawHtml(nodeColor(d.node_type))}">
            ${NODE_TYPE_LABELS[d.node_type] || d.node_type}
          </span>
          ${rawHtml(d.file_path ? `<p class="text-xs text-fg/60 mt-2 break-all">${escapeHtml(d.file_path)}${lineRange ? ':' + escapeHtml(String(lineRange)) : ''}</p>` : '')}
        </div>

        <div>
          <h4 class="text-xs font-heading text-fg/70">Incoming (${incoming.length})</h4>
          ${rawHtml(incoming.length
            ? `<ul class="mt-1 space-y-1">${incomingHtml}</ul>`
            : '<p class="text-xs text-fg/40 mt-1">None</p>')}
        </div>

        <div>
          <h4 class="text-xs font-heading text-fg/70">Outgoing (${outgoing.length})</h4>
          ${rawHtml(outgoing.length
            ? `<ul class="mt-1 space-y-1">${outgoingHtml}</ul>`
            : '<p class="text-xs text-fg/40 mt-1">None</p>')}
        </div>
      </div>`);

    // Close button
    detailPanel.querySelector('#graph-detail-close')?.addEventListener('click', () => {
      deselectNode();
    });
  }

  function deselectNode() {
    selectedNode = null;
    detailPanel.classList.add('hidden');
    detailPanel.replaceChildren();
    if (nodeSel) {
      nodeSel.attr('stroke-width', 2);
    }
  }

  // -- Zoom to a node's neighborhood ----------------------------------------

  function zoomToNode(d) {
    // Gather 1-hop neighbors
    const neighborIds = new Set([d.id]);
    for (const l of currentLinks) {
      const src = typeof l.source === 'object' ? l.source.id : l.source;
      const tgt = typeof l.target === 'object' ? l.target.id : l.target;
      if (src === d.id) neighborIds.add(tgt);
      if (tgt === d.id) neighborIds.add(src);
    }

    // Find bounding box of neighbors
    const neighborNodes = currentNodes.filter((n) => neighborIds.has(n.id));
    if (neighborNodes.length === 0) return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of neighborNodes) {
      if (n.x < minX) minX = n.x;
      if (n.y < minY) minY = n.y;
      if (n.x > maxX) maxX = n.x;
      if (n.y > maxY) maxY = n.y;
    }

    const padding = 80;
    minX -= padding;
    minY -= padding;
    maxX += padding;
    maxY += padding;

    const bboxWidth = maxX - minX;
    const bboxHeight = maxY - minY;
    const svgWidth = canvasEl.clientWidth || width;
    const svgHeight = canvasEl.clientHeight || height;
    const scale = Math.min(svgWidth / bboxWidth, svgHeight / bboxHeight, 4);
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;

    svg.transition()
      .duration(500)
      .call(
        zoom.transform,
        d3.zoomIdentity
          .translate(svgWidth / 2, svgHeight / 2)
          .scale(scale)
          .translate(-cx, -cy)
      );
  }

  // -- Search highlighting ---------------------------------------------------

  function applySearchHighlight() {
    if (!nodeSel) return;

    if (!searchQuery) {
      // Reset all opacity
      nodeSel.attr('opacity', 1);
      linkSel.attr('opacity', (d) => d.confidence ?? 0.6);
      if (labelSel) labelSel.attr('opacity', 0.85);
      return;
    }

    const q = searchQuery.toLowerCase();
    const matchIds = new Set();
    for (const n of currentNodes) {
      if (
        (n.name && n.name.toLowerCase().includes(q)) ||
        (n.file_path && n.file_path.toLowerCase().includes(q))
      ) {
        matchIds.add(n.id);
      }
    }

    nodeSel.attr('opacity', (d) => matchIds.has(d.id) ? 1.0 : 0.15);
    linkSel.attr('opacity', (d) => {
      const src = typeof d.source === 'object' ? d.source.id : d.source;
      const tgt = typeof d.target === 'object' ? d.target.id : d.target;
      return (matchIds.has(src) || matchIds.has(tgt)) ? (d.confidence ?? 0.6) : 0.05;
    });
    if (labelSel) {
      labelSel.attr('opacity', (d) => matchIds.has(d.id) ? 0.95 : 0.1);
    }
  }

  // -- Attach listeners ------------------------------------------------------

  // Search bar
  attachSearchListeners('graph-search', (query) => {
    searchQuery = query;
    applySearchHighlight();
  });

  // Node type filter chips
  attachFilterListeners('graph-node-chips', nodeTypes, activeNodeTypes, NODE_COLORS, (newSet) => {
    activeNodeTypes = newSet;
    rerenderChips();
    drawGraph();
  });

  // Edge type filter chips
  attachFilterListeners('graph-edge-chips', edgeTypes, activeEdgeTypes, EDGE_COLORS, (newSet) => {
    activeEdgeTypes = newSet;
    rerenderChips();
    drawGraph();
  });

  // Node limit input
  nodeLimitInput.addEventListener('change', () => {
    const val = parseInt(nodeLimitInput.value, 10);
    if (!isNaN(val) && val >= 10) {
      nodeLimit = val;
      drawGraph();
    }
  }, { signal });

  // Reset zoom button
  resetZoomBtn.addEventListener('click', () => {
    const svgWidth = canvasEl.clientWidth || width;
    const svgHeight = canvasEl.clientHeight || height;
    svg.transition()
      .duration(400)
      .call(zoom.transform, d3.zoomIdentity.translate(0, 0).scale(1));
  }, { signal });

  // Resize observer: update SVG viewBox on container resize
  const resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const { width: w, height: h } = entry.contentRect;
      if (w > 0 && h > 0) {
        svg.attr('viewBox', `0 0 ${w} ${h}`);
      }
    }
  });
  resizeObserver.observe(canvasEl);

  // -- Re-render filter chips (after state change) ---------------------------

  function rerenderChips() {
    const nodeChipContainer = container.querySelector('#graph-node-chips');
    const edgeChipContainer = container.querySelector('#graph-edge-chips');

    if (nodeChipContainer) {
      setHTML(nodeChipContainer, filterChips({
        items: nodeTypes,
        activeSet: activeNodeTypes,
        colorMap: NODE_COLORS,
        onChange: () => {},
      }));
      attachFilterListeners('graph-node-chips', nodeTypes, activeNodeTypes, NODE_COLORS, (newSet) => {
        activeNodeTypes = newSet;
        rerenderChips();
        drawGraph();
      });
    }

    if (edgeChipContainer) {
      setHTML(edgeChipContainer, filterChips({
        items: edgeTypes,
        activeSet: activeEdgeTypes,
        colorMap: EDGE_COLORS,
        onChange: () => {},
      }));
      attachFilterListeners('graph-edge-chips', edgeTypes, activeEdgeTypes, EDGE_COLORS, (newSet) => {
        activeEdgeTypes = newSet;
        rerenderChips();
        drawGraph();
      });
    }
  }

  // -- Initial draw ----------------------------------------------------------
  drawGraph();

  // -- Cleanup ---------------------------------------------------------------
  return () => {
    if (simulation) {
      simulation.stop();
      simulation = null;
    }
    ac.abort();
    resizeObserver.disconnect();
    hideTooltip();
  };
}
