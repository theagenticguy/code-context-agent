// dependencies.js — Dependency chain explorer with D3 tree layout
// Allows searching for a node and visualizing its upstream/downstream dependency chain
// as a collapsible tree.

import { store } from '../store.js';
import { searchBar } from '../components/search-bar.js';
import { showTooltip, hideTooltip } from '../components/tooltip.js';
import { edgeColor, nodeColor } from '../colors.js';
import { getDependencyChain, shortPath } from '../graph-utils.js';
import { DEPENDENCY_EDGE_TYPES } from '../colors.js';
import { escapeHtml, safeHtml, rawHtml } from '../escape.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const VIEW_ID = 'dep-explorer';
const DEFAULT_DEPTH = 3;
const MAX_DEPTH = 6;
const MIN_DEPTH = 1;
const AUTOCOMPLETE_LIMIT = 10;
const NODE_RADIUS = 6;
const TRANSITION_MS = 300;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Convert a flat dependency chain (from getDependencyChain) into a d3-hierarchy
 * tree rooted at the selected node.
 *
 * @param {object} rootNode - The selected graph node
 * @param {Array<{node: object, depth: number, edge: object}>} chain - BFS results
 * @returns {object} Tree root with { name, data, children } structure
 */
function chainToHierarchy(rootNode, chain) {
  const root = {
    name: rootNode.name,
    data: { ...rootNode, depth: 0, edge: null },
    children: [],
  };

  // Group chain entries by depth, then build parent-child by BFS order
  // We need to reconstruct the tree from the flat BFS results.
  // Build a map of nodeId -> tree node, attach children by re-traversing adjacency.
  const treeNodes = new Map();
  treeNodes.set(rootNode.id, root);

  // Sort by depth to process parents before children
  const sorted = [...chain].sort((a, b) => a.depth - b.depth);

  for (const entry of sorted) {
    const treeNode = {
      name: entry.node.name,
      data: { ...entry.node, depth: entry.depth, edge: entry.edge },
      children: [],
    };
    treeNodes.set(entry.node.id, treeNode);
  }

  // Now link children to parents using the edge info
  for (const entry of sorted) {
    const childTreeNode = treeNodes.get(entry.node.id);
    // The parent is the source (downstream) or target (upstream) of the edge
    const parentId = entry.edge.source === entry.node.id
      ? entry.edge.target
      : entry.edge.source;
    const parentTreeNode = treeNodes.get(parentId);
    if (parentTreeNode) {
      parentTreeNode.children.push(childTreeNode);
    } else {
      // Orphan — attach to root as fallback
      root.children.push(childTreeNode);
    }
  }

  return root;
}

/**
 * Filter graph nodes matching a search query.
 * @param {object} graph - CodeGraph
 * @param {string} query - Search string
 * @returns {Array<object>} Matched nodes (up to AUTOCOMPLETE_LIMIT)
 */
function searchNodes(graph, query) {
  if (!graph || !query) return [];
  const q = query.toLowerCase();
  return graph.nodes
    .filter(
      (n) =>
        (n.name && n.name.toLowerCase().includes(q)) ||
        (n.file_path && n.file_path.toLowerCase().includes(q)) ||
        (n.id && n.id.toLowerCase().includes(q))
    )
    .slice(0, AUTOCOMPLETE_LIMIT);
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

/**
 * Render the dependency explorer view.
 *
 * @param {HTMLElement} container - The #content element
 * @param {import('../store.js').Store} appStore - The global store
 * @returns {() => void} Cleanup function
 */
export function render(container, appStore) {
  const graph = appStore.get('graph');

  // -- No graph loaded state --
  if (!graph) {
    // nosemgrep: javascript.browser.security.insecure-document-method.insecure-document-method
    // Static HTML with no interpolated data values.
    container.innerHTML = `
      <div class="flex items-center justify-center h-full">
        <div class="text-center">
          <p class="text-2xl font-heading mb-2">Load data first</p>
          <p class="text-fg/50 text-sm">Drop code_graph.json to get started</p>
        </div>
      </div>`;
    return () => {};
  }

  // -- Local state --
  let selectedNode = null;
  let direction = 'downstream';
  let depth = DEFAULT_DEPTH;
  let autocompleteResults = [];
  let showAutocomplete = false;

  // -- Layout --
  container.innerHTML = safeHtml` // nosemgrep: javascript.browser.security.insecure-document-method.insecure-document-method
    <div id="${rawHtml(VIEW_ID)}" class="flex flex-col h-full view-enter">
      <!-- Controls bar -->
      <div class="flex flex-wrap items-end gap-3 p-4 border-b-2 border-border bg-bg2">
        <!-- Search with autocomplete -->
        <div class="flex-1 min-w-[220px] relative" id="${rawHtml(VIEW_ID)}-search-wrap">
          ${rawHtml(searchBar({ placeholder: 'Find a node...' }))}
          <div id="${rawHtml(VIEW_ID)}-autocomplete"
               class="absolute left-0 right-0 top-full mt-1 z-50 hidden
                      rounded-base border-2 border-border bg-bg2 shadow-neo
                      max-h-64 overflow-auto">
          </div>
        </div>

        <!-- Direction toggle -->
        <div class="flex flex-col gap-1">
          <span class="text-[10px] uppercase tracking-wide text-fg/50 font-base">Direction</span>
          <button id="${rawHtml(VIEW_ID)}-dir-toggle"
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-base
                         border-2 border-border font-base neo-pressable bg-bg2">
            <span id="${rawHtml(VIEW_ID)}-dir-icon">\u25BC</span>
            <span id="${rawHtml(VIEW_ID)}-dir-label">Downstream</span>
          </button>
        </div>

        <!-- Depth slider -->
        <div class="flex flex-col gap-1">
          <span class="text-[10px] uppercase tracking-wide text-fg/50 font-base">
            Depth: <span id="${rawHtml(VIEW_ID)}-depth-val">${depth}</span>
          </span>
          <input id="${rawHtml(VIEW_ID)}-depth-slider" type="range"
                 min="${MIN_DEPTH}" max="${MAX_DEPTH}" value="${depth}"
                 class="w-28 h-2 accent-main cursor-pointer" />
        </div>

        <!-- Selected node indicator -->
        <div id="${rawHtml(VIEW_ID)}-selected" class="hidden flex items-center gap-2 px-3 py-1.5 text-xs
                    rounded-base border-2 border-border bg-bg2 font-base">
          <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" id="${rawHtml(VIEW_ID)}-sel-dot"></span>
          <span id="${rawHtml(VIEW_ID)}-sel-name" class="truncate-line max-w-[180px]"></span>
          <button id="${rawHtml(VIEW_ID)}-sel-clear" class="ml-1 text-fg/40 hover:text-fg">\u2715</button>
        </div>
      </div>

      <!-- D3 tree area -->
      <div id="${rawHtml(VIEW_ID)}-tree" class="flex-1 relative overflow-hidden bg-bg">
        <div id="${rawHtml(VIEW_ID)}-empty" class="flex items-center justify-center h-full">
          <p class="text-fg/40 text-sm">Search for a node to explore its dependencies</p>
        </div>
        <svg id="${rawHtml(VIEW_ID)}-svg" class="hidden w-full h-full"></svg>
      </div>
    </div>`;

  // -- DOM references --
  const searchWrap = document.getElementById(`${VIEW_ID}-search-wrap`);
  const searchInput = searchWrap?.querySelector('[data-search-input]');
  const acDropdown = document.getElementById(`${VIEW_ID}-autocomplete`);
  const dirToggle = document.getElementById(`${VIEW_ID}-dir-toggle`);
  const dirIcon = document.getElementById(`${VIEW_ID}-dir-icon`);
  const dirLabel = document.getElementById(`${VIEW_ID}-dir-label`);
  const depthSlider = document.getElementById(`${VIEW_ID}-depth-slider`);
  const depthVal = document.getElementById(`${VIEW_ID}-depth-val`);
  const selectedIndicator = document.getElementById(`${VIEW_ID}-selected`);
  const selDot = document.getElementById(`${VIEW_ID}-sel-dot`);
  const selName = document.getElementById(`${VIEW_ID}-sel-name`);
  const selClear = document.getElementById(`${VIEW_ID}-sel-clear`);
  const treeContainer = document.getElementById(`${VIEW_ID}-tree`);
  const emptyState = document.getElementById(`${VIEW_ID}-empty`);
  const svg = document.getElementById(`${VIEW_ID}-svg`);

  // -- Autocomplete --
  function renderAutocomplete(results) {
    if (!results.length) {
      acDropdown.classList.add('hidden');
      return;
    }
    acDropdown.classList.remove('hidden');
    acDropdown.innerHTML = results // nosemgrep: javascript.browser.security.insecure-document-method.insecure-document-method
      .map(
        (n) => `
        <button data-ac-id="${escapeHtml(n.id)}"
                class="w-full text-left px-3 py-2 text-xs font-base hover:bg-main/20
                       flex items-center gap-2 border-b border-border/20 last:border-b-0
                       transition-colors">
          <span class="w-2 h-2 rounded-full flex-shrink-0" style="background: ${nodeColor(n.node_type)}"></span>
          <span class="font-heading truncate-line">${escapeHtml(n.name)}</span>
          <span class="text-fg/40 ml-auto truncate-line max-w-[200px]">${escapeHtml(shortPath(n.file_path))}</span>
        </button>`
      )
      .join('');

    // Click handlers
    acDropdown.querySelectorAll('[data-ac-id]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const nodeId = btn.getAttribute('data-ac-id');
        const node = graph.nodes.find((n) => n.id === nodeId);
        if (node) selectNode(node);
        acDropdown.classList.add('hidden');
        if (searchInput) searchInput.value = '';
      });
    });
  }

  function onSearchInput(query) {
    if (!query) {
      acDropdown.classList.add('hidden');
      return;
    }
    autocompleteResults = searchNodes(graph, query);
    renderAutocomplete(autocompleteResults);
  }

  // -- Attach search debounce --
  let searchTimer = null;
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        onSearchInput(searchInput.value.trim());
      }, 200);
    });

    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        searchInput.value = '';
        acDropdown.classList.add('hidden');
        clearTimeout(searchTimer);
        searchInput.blur();
      }
    });

    // Close autocomplete when clicking outside
    document.addEventListener('click', handleClickOutside);
  }

  function handleClickOutside(e) {
    if (searchWrap && !searchWrap.contains(e.target)) {
      acDropdown?.classList.add('hidden');
    }
  }

  // -- Direction toggle --
  dirToggle?.addEventListener('click', () => {
    direction = direction === 'downstream' ? 'upstream' : 'downstream';
    dirIcon.textContent = direction === 'downstream' ? '\u25BC' : '\u25B2';
    dirLabel.textContent = direction === 'downstream' ? 'Downstream' : 'Upstream';
    if (selectedNode) renderTree();
  });

  // -- Depth slider --
  depthSlider?.addEventListener('input', () => {
    depth = parseInt(depthSlider.value, 10);
    depthVal.textContent = depth;
    if (selectedNode) renderTree();
  });

  // -- Clear selection --
  selClear?.addEventListener('click', () => {
    selectedNode = null;
    selectedIndicator?.classList.add('hidden');
    svg?.classList.add('hidden');
    emptyState?.classList.remove('hidden');
    // nosemgrep: javascript.browser.security.insecure-document-method.insecure-document-method
    // Static HTML with no interpolated data values.
    emptyState.innerHTML = `
      <p class="text-fg/40 text-sm">Search for a node to explore its dependencies</p>`;
  });

  // -- Node selection --
  function selectNode(node) {
    selectedNode = node;

    // Update indicator
    selectedIndicator?.classList.remove('hidden');
    if (selDot) selDot.style.background = nodeColor(node.node_type);
    if (selName) selName.textContent = node.name;

    renderTree();
  }

  // -- D3 Tree rendering --
  function renderTree() {
    if (!selectedNode) return;

    const chain = getDependencyChain(graph, selectedNode.id, direction, depth);

    // No results
    if (!chain.length) {
      svg?.classList.add('hidden');
      emptyState?.classList.remove('hidden');
      emptyState.innerHTML = safeHtml` // nosemgrep: javascript.browser.security.insecure-document-method.insecure-document-method
        <p class="text-fg/40 text-sm">No dependency chain found for <strong>${selectedNode.name}</strong>
        (${direction})</p>`;
      return;
    }

    // Build hierarchy
    const hierarchyData = chainToHierarchy(selectedNode, chain);
    const root = d3.hierarchy(hierarchyData);

    // Compute layout
    const nodeCount = root.descendants().length;
    const nodeSpacingY = 32;
    const nodeSpacingX = 220;
    const treeHeight = Math.max(nodeCount * nodeSpacingY, 200);

    const treeLayout = d3.tree().nodeSize([nodeSpacingY, nodeSpacingX]);
    treeLayout(root);

    // Show SVG, hide empty
    emptyState?.classList.add('hidden');
    svg?.classList.remove('hidden');

    const d3svg = d3.select(svg);
    d3svg.selectAll('*').remove();

    // Compute bounding box of all nodes
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    root.descendants().forEach((d) => {
      if (d.x < minX) minX = d.x;
      if (d.x > maxX) maxX = d.x;
      if (d.y < minY) minY = d.y;
      if (d.y > maxY) maxY = d.y;
    });

    const padding = 60;
    const svgWidth = treeContainer.clientWidth;
    const svgHeight = treeContainer.clientHeight;
    const treeW = maxY - minY + padding * 2;
    const treeH = maxX - minX + padding * 2;

    // Set viewBox for zoom/pan
    d3svg.attr('viewBox', `${minY - padding} ${minX - padding} ${treeW} ${treeH}`);

    // Enable zoom + pan
    const zoom = d3.zoom()
      .scaleExtent([0.2, 4])
      .on('zoom', (event) => {
        gRoot.attr('transform', event.transform);
      });

    d3svg.call(zoom);

    // Reset viewBox and use transform-based zoom instead
    d3svg.attr('viewBox', null);
    d3svg.attr('width', svgWidth);
    d3svg.attr('height', svgHeight);

    const gRoot = d3svg.append('g')
      .attr('transform', `translate(${padding}, ${svgHeight / 2 - (minX + maxX) / 2})`);

    // -- Collapsible state --
    // Store _children for collapsed nodes
    root.descendants().forEach((d) => {
      d._children = null;
    });

    drawTree(gRoot, root);

    // Fit initial view
    const initialScale = Math.min(
      svgWidth / (treeW || 1),
      svgHeight / (treeH || 1),
      1.5
    );
    const tx = svgWidth / 2 - ((minY + maxY) / 2 + padding) * initialScale;
    const ty = svgHeight / 2 - ((minX + maxX) / 2 + padding) * initialScale;
    d3svg.call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(initialScale));
  }

  /**
   * Draw (or update) the tree links and nodes.
   * @param {d3.Selection} g - The root <g> element
   * @param {d3.HierarchyNode} root - The hierarchy root
   */
  function drawTree(g, root) {
    g.selectAll('*').remove();

    const nodes = root.descendants();
    const links = root.links();

    // -- Links --
    const linkGenerator = d3.linkHorizontal()
      .x((d) => d.y)
      .y((d) => d.x);

    g.selectAll('.dep-link')
      .data(links)
      .join('path')
      .attr('class', 'dep-link')
      .attr('d', linkGenerator)
      .attr('fill', 'none')
      .attr('stroke', (d) => {
        const edge = d.target.data.data?.edge;
        return edge ? edgeColor(edge.edge_type) : '#71717a';
      })
      .attr('stroke-width', 2)
      .attr('stroke-opacity', (d) => {
        const edge = d.target.data.data?.edge;
        return edge?.confidence != null ? Math.max(0.3, edge.confidence) : 0.7;
      });

    // -- Nodes --
    const nodeGroups = g.selectAll('.dep-node')
      .data(nodes)
      .join('g')
      .attr('class', 'dep-node')
      .attr('transform', (d) => `translate(${d.y},${d.x})`)
      .style('cursor', 'pointer');

    // Circle
    nodeGroups.append('circle')
      .attr('r', (d) => d.data.data?.depth === 0 ? NODE_RADIUS + 2 : NODE_RADIUS)
      .attr('fill', (d) => nodeColor(d.data.data?.node_type))
      .attr('stroke', 'var(--border)')
      .attr('stroke-width', 2);

    // Collapse indicator (small +/- inside circle for nodes with children)
    nodeGroups.filter((d) => d.children || d._children)
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('font-size', '9px')
      .attr('font-weight', '700')
      .attr('fill', 'var(--foreground)')
      .attr('pointer-events', 'none')
      .text((d) => d._children ? '+' : (d.children ? '\u2212' : ''));

    // Label: name
    nodeGroups.append('text')
      .attr('dy', '0.32em')
      .attr('x', (d) => (d.children || d._children) ? -12 : 12)
      .attr('text-anchor', (d) => (d.children || d._children) ? 'end' : 'start')
      .attr('font-size', '11px')
      .attr('font-weight', (d) => d.data.data?.depth === 0 ? '700' : '500')
      .attr('fill', 'var(--foreground)')
      .text((d) => d.data.name);

    // Sublabel: file path
    nodeGroups.append('text')
      .attr('dy', '1.5em')
      .attr('x', (d) => (d.children || d._children) ? -12 : 12)
      .attr('text-anchor', (d) => (d.children || d._children) ? 'end' : 'start')
      .attr('font-size', '9px')
      .attr('fill', 'var(--foreground)')
      .attr('opacity', 0.45)
      .text((d) => shortPath(d.data.data?.file_path));

    // -- Tooltip --
    nodeGroups
      .on('mouseenter', (event, d) => {
        const nd = d.data.data;
        if (!nd) return;
        const edge = nd.edge;
        const edgeInfo = edge
          ? `<div class="mt-1 pt-1 border-t border-border/30">
               <span style="color: ${edgeColor(edge.edge_type)}">${escapeHtml(edge.edge_type)}</span>
               ${edge.confidence != null ? ` <span class="text-fg/40">(${(edge.confidence * 100).toFixed(0)}%)</span>` : ''}
             </div>`
          : '';
        showTooltip(
          safeHtml`<div>
            <strong>${nd.name}</strong>
            <span class="text-fg/50 ml-1">${nd.node_type}</span>
          </div>
          <div class="text-fg/50 text-[10px]">${nd.file_path || ''}</div>
          ${rawHtml(edgeInfo)}`,
          event.clientX,
          event.clientY
        );
      })
      .on('mouseleave', () => hideTooltip());

    // -- Click to collapse/expand --
    nodeGroups.on('click', (event, d) => {
      event.stopPropagation();
      hideTooltip();

      if (d.children) {
        // Collapse
        d._children = d.children;
        d.children = null;
      } else if (d._children) {
        // Expand
        d.children = d._children;
        d._children = null;
      } else {
        // Leaf node — recenter the tree on this node
        const clickedNode = d.data.data;
        if (clickedNode && clickedNode.id && clickedNode.id !== selectedNode?.id) {
          const node = graph.nodes.find((n) => n.id === clickedNode.id);
          if (node) selectNode(node);
        }
        return;
      }

      // Re-layout
      const treeLayout = d3.tree().nodeSize([32, 220]);
      treeLayout(root);
      drawTree(g, root);
    });
  }

  // -- Cleanup --
  return function cleanup() {
    document.removeEventListener('click', handleClickOutside);
    clearTimeout(searchTimer);
    hideTooltip();
  };
}
