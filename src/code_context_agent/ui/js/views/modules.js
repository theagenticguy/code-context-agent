// modules.js — D3 circle-packing visualization of code modules
// Groups symbols by file-path hierarchy and renders zoomable packed circles.

import { showTooltip, hideTooltip } from '../components/tooltip.js';
import { nodeColor } from '../colors.js';
import { buildHierarchy } from '../graph-utils.js';
import { escapeHtml, safeHtml, rawHtml, setHTML } from '../escape.js';

const d3 = window.d3;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a type-breakdown HTML snippet for a hierarchy node.
 * Counts leaf node_type values within the subtree.
 * @param {d3.HierarchyNode} node
 * @returns {string}
 */
function typeBreakdownHtml(node) {
  const counts = {};
  for (const leaf of node.leaves()) {
    const t = leaf.data.node_type || 'unknown';
    counts[t] = (counts[t] || 0) + 1;
  }
  const lines = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(
      ([type, count]) =>
        `<span style="color:${nodeColor(type)}; font-weight:700;">${escapeHtml(type)}</span>: ${count}`
    )
    .join('<br>');
  return lines;
}

/**
 * Build the full path string for a hierarchy node by walking ancestors.
 * @param {d3.HierarchyNode} node
 * @returns {string}
 */
function ancestorPath(node) {
  const parts = [];
  let cur = node;
  while (cur && cur.parent) {
    parts.unshift(cur.data.name);
    cur = cur.parent;
  }
  return parts.join('/') || 'root';
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

/**
 * Render the modules circle-packing view.
 * @param {HTMLElement} container
 * @param {import('../store.js').Store} st
 * @returns {() => void} cleanup function
 */
export function render(container, st) {
  const graph = st.get('graph');

  // ---- Empty state --------------------------------------------------------
  if (!graph || !graph.nodes || graph.nodes.length === 0) {
    setHTML(container, `
      <div class="flex flex-col items-center justify-center h-full gap-4 p-8">
        <span class="text-5xl">&#x29C9;</span>
        <h2 class="font-heading text-xl">No Module Data</h2>
        <p class="text-sm text-fg/50 font-base max-w-md text-center">
          Drop a <code class="px-1 py-0.5 rounded-base border border-border/40 bg-bg text-xs font-mono">code_graph.json</code>
          file onto the page to visualize module structure.
        </p>
      </div>`);
    return () => {};
  }

  // ---- State --------------------------------------------------------------
  let focus = null; // currently zoomed-into hierarchy node
  let resizeObserver = null;

  // ---- Shell HTML ---------------------------------------------------------
  setHTML(container, `
    <div class="flex flex-col h-full">
      <!-- Title bar -->
      <div class="flex items-center gap-3 px-5 py-3 border-b-2 border-border bg-bg2">
        <span class="text-lg">&#x29C9;</span>
        <h2 class="font-heading text-base tracking-tight">Modules</h2>
        <span id="mod-count" class="text-xs text-fg/50 font-base"></span>
        <div id="mod-breadcrumb" class="ml-auto flex items-center gap-1 text-xs font-base text-fg/60"></div>
      </div>
      <!-- SVG canvas -->
      <div id="mod-canvas" class="flex-1 relative overflow-hidden bg-bg"></div>
    </div>`);

  const canvasEl = container.querySelector('#mod-canvas');
  const countEl = container.querySelector('#mod-count');
  const breadcrumbEl = container.querySelector('#mod-breadcrumb');

  // ---- Build hierarchy & pack --------------------------------------------
  const treeData = buildHierarchy(graph);
  const hierarchy = d3
    .hierarchy(treeData)
    .sum((d) => (d.children ? 0 : 1))
    .sort((a, b) => b.value - a.value);

  countEl.textContent = `${graph.nodes.length} nodes`;

  // ---- SVG setup ----------------------------------------------------------
  const svg = d3
    .select(canvasEl)
    .append('svg')
    .attr('width', '100%')
    .attr('height', '100%')
    .style('display', 'block')
    .style('cursor', 'pointer');

  const g = svg.append('g');

  // ---- Layout & draw function (called on resize) -------------------------
  function layout() {
    const { width, height } = canvasEl.getBoundingClientRect();
    if (width === 0 || height === 0) return;

    svg.attr('viewBox', `0 0 ${width} ${height}`);

    const pack = d3.pack().size([width, height]).padding(3);
    const root = pack(hierarchy);

    // Set initial focus to root
    if (!focus) focus = root;

    drawCircles(root, width, height);
  }

  // ---- Draw circles -------------------------------------------------------
  function drawCircles(root, width, height) {
    g.selectAll('*').remove();

    const nodes = root.descendants();

    // Compute initial zoom transform for current focus
    const k = width / (focus.r * 2);
    const tx = width / 2 - focus.x * k;
    const ty = height / 2 - focus.y * k;

    // Circle groups
    const node = g
      .selectAll('g')
      .data(nodes)
      .join('g')
      .attr('transform', (d) => `translate(${d.x * k + tx},${d.y * k + ty})`);

    // Circles
    node
      .append('circle')
      .attr('r', (d) => Math.max(0, d.r * k))
      .attr('fill', (d) => {
        if (d.children) return nodeColor(d.data.node_type || 'module');
        return nodeColor(d.data.node_type || 'unknown');
      })
      .attr('fill-opacity', (d) => (d.children ? 0.08 : 0.7))
      .attr('stroke', (d) => {
        if (d.children) return nodeColor(d.data.node_type || 'module');
        return nodeColor(d.data.node_type || 'unknown');
      })
      .attr('stroke-width', (d) => (d.children ? 1.5 : 1))
      .attr('stroke-opacity', (d) => (d.children ? 0.5 : 0.9));

    // Labels
    node
      .append('text')
      .text((d) => d.data.name)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('fill', 'var(--foreground)')
      .attr('opacity', (d) => {
        const r = d.r * k;
        // Only show label if circle is large enough
        if (d.children) return r > 30 ? 0.7 : 0;
        return r > 12 ? 0.9 : 0;
      })
      .style('font-size', (d) => {
        const r = d.r * k;
        if (d.children) return `${Math.min(12, Math.max(8, r / 5))}px`;
        return `${Math.min(11, Math.max(7, r / 3))}px`;
      })
      .style('font-family', 'inherit')
      .style('font-weight', (d) => (d.children ? '700' : '500'))
      .style('pointer-events', 'none')
      .each(function (d) {
        // Clip text that overflows the circle
        const r = d.r * k;
        const maxWidth = r * 1.6;
        const textEl = d3.select(this);
        let text = d.data.name;
        if (this.getComputedTextLength && this.getComputedTextLength() > maxWidth) {
          while (text.length > 3 && this.getComputedTextLength() > maxWidth) {
            text = text.slice(0, -1);
            textEl.text(text + '\u2026');
          }
        }
      });

    // ---- Interactions -----------------------------------------------------

    // Hover tooltip
    node
      .on('mouseenter', (event, d) => {
        const path = ancestorPath(d);
        const memberCount = d.value || 0;
        let html = safeHtml`<div style="margin-bottom:4px;"><strong>${d.data.name}</strong></div>`;
        html += safeHtml`<div style="color:var(--foreground);opacity:0.6;font-size:11px;margin-bottom:4px;">${path}</div>`;
        html += safeHtml`<div style="margin-bottom:4px;">Members: <strong>${String(memberCount)}</strong></div>`;
        if (d.children) {
          html += typeBreakdownHtml(d);
        } else if (d.data.node_type) {
          html += `<span style="color:${nodeColor(d.data.node_type)}; font-weight:700;">${escapeHtml(d.data.node_type)}</span>`;
        }
        showTooltip(html, event.clientX, event.clientY);

        // Highlight circle
        d3.select(event.currentTarget)
          .select('circle')
          .transition()
          .duration(150)
          .attr('stroke-width', (d) => (d.children ? 2.5 : 2))
          .attr('fill-opacity', (d) => (d.children ? 0.15 : 0.85));
      })
      .on('mousemove', (event) => {
        const el = document.getElementById('tooltip');
        if (el && el.classList.contains('visible')) {
          const rect = el.getBoundingClientRect();
          const left = Math.min(event.clientX + 12, window.innerWidth - rect.width - 8);
          const top = Math.min(event.clientY - 8, window.innerHeight - rect.height - 8);
          el.style.left = Math.max(8, left) + 'px';
          el.style.top = Math.max(8, top) + 'px';
        }
      })
      .on('mouseleave', (event, d) => {
        hideTooltip();
        d3.select(event.currentTarget)
          .select('circle')
          .transition()
          .duration(150)
          .attr('stroke-width', (d) => (d.children ? 1.5 : 1))
          .attr('fill-opacity', (d) => (d.children ? 0.08 : 0.7));
      });

    // Click to zoom
    node
      .filter((d) => d.children) // only zoomable nodes (non-leaves)
      .on('click', (event, d) => {
        event.stopPropagation();
        zoomTo(d, root, width, height);
      });

    // Click background to zoom out
    svg.on('click', () => {
      zoomTo(root, root, width, height);
    });

    updateBreadcrumb(root, width, height);
  }

  // ---- Zoom animation -----------------------------------------------------
  function zoomTo(target, root, width, height) {
    focus = target;

    const k = width / (target.r * 2);
    const tx = width / 2 - target.x * k;
    const ty = height / 2 - target.y * k;

    const nodes = root.descendants();

    const t = d3.transition().duration(500).ease(d3.easeCubicInOut);

    g.selectAll('g')
      .data(nodes)
      .transition(t)
      .attr('transform', (d) => `translate(${d.x * k + tx},${d.y * k + ty})`);

    g.selectAll('circle')
      .data(nodes)
      .transition(t)
      .attr('r', (d) => Math.max(0, d.r * k));

    g.selectAll('text')
      .data(nodes)
      .transition(t)
      .attr('opacity', (d) => {
        const r = d.r * k;
        if (d.children) return r > 30 ? 0.7 : 0;
        return r > 12 ? 0.9 : 0;
      })
      .style('font-size', (d) => {
        const r = d.r * k;
        if (d.children) return `${Math.min(12, Math.max(8, r / 5))}px`;
        return `${Math.min(11, Math.max(7, r / 3))}px`;
      });

    updateBreadcrumb(root, width, height);
  }

  // ---- Breadcrumb ---------------------------------------------------------
  function updateBreadcrumb(root, width, height) {
    const crumbs = [];
    let cur = focus;
    while (cur) {
      crumbs.unshift(cur);
      cur = cur.parent;
    }

    setHTML(breadcrumbEl, crumbs
      .map((node, i) => {
        const isLast = i === crumbs.length - 1;
        const name = node.data.name === 'root' ? 'root' : node.data.name;
        const separator = i > 0 ? rawHtml('<span class="text-fg/30 mx-0.5">/</span>') : '';
        if (isLast) {
          return safeHtml`${separator}<span class="text-fg font-heading">${name}</span>`;
        }
        return safeHtml`${separator}<button class="hover:text-main hover:underline transition-colors breadcrumb-btn" data-depth="${i}">${name}</button>`;
      })
      .join(''));

    // Wire up breadcrumb clicks
    breadcrumbEl.querySelectorAll('.breadcrumb-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const depth = parseInt(btn.dataset.depth, 10);
        const target = crumbs[depth];
        if (target) {
          zoomTo(target, root, width, height);
        }
      });
    });
  }

  // ---- Responsive ---------------------------------------------------------
  resizeObserver = new ResizeObserver(() => {
    // Reset focus to root on resize to avoid stale coordinates
    focus = null;
    layout();
  });
  resizeObserver.observe(canvasEl);

  // Initial render
  layout();

  // ---- Store subscription -------------------------------------------------
  const unsub = st.on('graph', () => {
    // If graph changes, re-render the entire view
    render(container, st);
  });

  // ---- Cleanup ------------------------------------------------------------
  return () => {
    unsub();
    hideTooltip();
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver = null;
    }
    svg.on('click', null);
    container.replaceChildren();
  };
}
