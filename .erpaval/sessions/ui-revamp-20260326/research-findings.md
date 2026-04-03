# UI Technology Research Report
**Date:** 2026-03-26
**Purpose:** Pre-coding research for a pure HTML/CSS/JS UI project using neobrutalism design, Tailwind v4, D3.js, and vanilla architecture

---

## 1. Neobrutalism Components — CSS Design System

### Source Repository
- **Repo:** https://github.com/ekmas/neobrutalism-components
- **Framework:** React + Next.js + Tailwind CSS v4 (but design tokens are pure CSS)
- **Styling Engine:** Tailwind CSS v4 with `@theme inline` directive
- **Variant System:** class-variance-authority (cva) — React-specific, not needed for pure CSS

### Design Tokens (CSS Variables)

All tokens are defined in `src/styling/globals.css` using CSS custom properties and mapped to Tailwind via `@theme inline`.

#### Color Palette (OKLCH Color Space)

**Light Mode:**
```css
:root {
  --background: oklch(93.46% 0.0304 254.32);    /* Light blue-gray */
  --secondary-background: oklch(100% 0 0);        /* White */
  --foreground: oklch(0% 0 0);                     /* Black */
  --main-foreground: oklch(0% 0 0);                /* Black (text on accent) */
  --main: oklch(67.47% 0.1725 259.61);             /* Blue accent */
  --border: oklch(0% 0 0);                         /* Black */
  --ring: oklch(0% 0 0);                           /* Black */
  --overlay: oklch(0% 0 0 / 0.8);                  /* Black 80% opacity */
}
```

**Dark Mode:**
```css
.dark {
  --background: oklch(29.12% 0.0633 270.86);       /* Dark blue-gray */
  --secondary-background: oklch(23.93% 0 0);       /* Very dark gray */
  --foreground: oklch(92.49% 0 0);                  /* Near-white */
  --ring: oklch(100% 0 0);                          /* White */
}
```

**Chart Colors (for data visualization):**
```css
:root {
  --chart-1: oklch(67.47% 0.1726 259.49);   /* Blue */
  --chart-2: oklch(67.28% 0.2147 24.22);    /* Red-orange */
  --chart-3: oklch(86.03% 0.176 92.36);     /* Yellow */
  --chart-4: oklch(79.76% 0.2044 153.08);   /* Green */
  --chart-5: oklch(66.34% 0.1806 277.2);    /* Purple */
  --chart-active-dot: #000;                  /* Black (white in dark mode) */
}
```

#### Border System
- **Width:** `border-2` (2px) — consistent across ALL components
- **Color:** `border-border` → resolves to `var(--border)` → `oklch(0% 0 0)` (black)
- **Radius:** `rounded-base` → `var(--border-radius)` → `5px` default

#### Box Shadow System (THE signature neobrutalism pattern)
```css
:root {
  --box-shadow-x: 4px;
  --box-shadow-y: 4px;
  --reverse-box-shadow-x: -4px;
  --reverse-box-shadow-y: -4px;
  --shadow: var(--box-shadow-x) var(--box-shadow-y) 0px 0px var(--border);
}
```

**Key insight:** The shadow is a HARD shadow (0px blur, 0px spread) offset by 4px in both directions, colored with the border color (black). This creates the distinctive neobrutalist "stacked paper" or "3D block" effect.

**Hover interaction pattern ("pressed" effect):**
```
hover:translate-x-boxShadowX hover:translate-y-boxShadowY hover:shadow-none
```
On hover, the element translates by the shadow offset (4px, 4px) AND the shadow disappears — creating the illusion of pressing the element flat against the surface.

**Reverse variant:** Uses negative offset for the opposite direction.

#### Typography
```css
:root {
  --heading-font-weight: 700;   /* Bold headings */
  --base-font-weight: 500;      /* Medium body text */
}
```
- Headings: `font-heading` → `font-weight: 700`
- Body: `font-base` → `font-weight: 500`

#### Tailwind v4 Theme Mapping

The `@theme inline` directive in globals.css maps CSS variables to Tailwind utilities:

```css
@theme inline {
  /* Colors */
  --color-main: var(--main);
  --color-background: var(--background);
  --color-secondary-background: var(--secondary-background);
  --color-foreground: var(--foreground);
  --color-main-foreground: var(--main-foreground);
  --color-border: var(--border);
  --color-overlay: var(--overlay);
  --color-ring: var(--ring);

  /* Spacing (for translate utilities) */
  --spacing-boxShadowX: var(--box-shadow-x);
  --spacing-boxShadowY: var(--box-shadow-y);
  --spacing-reverseBoxShadowX: var(--reverse-box-shadow-x);
  --spacing-reverseBoxShadowY: var(--reverse-box-shadow-y);
  --spacing-container: 1300px;

  /* Border Radius */
  --radius-base: var(--border-radius);

  /* Shadows */
  --shadow-shadow: var(--shadow);
  --shadow-nav: 4px 4px 0px 0px var(--border);

  /* Font Weight */
  --font-weight-base: var(--base-font-weight);
  --font-weight-heading: var(--heading-font-weight);
}
```

### Component Patterns (CSS Classes Only)

#### Button Component
```
Base:     inline-flex items-center justify-center whitespace-nowrap rounded-base
          text-sm font-base ring-offset-white transition-all gap-2
          focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-black
          focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50

default:  text-main-foreground bg-main border-2 border-border shadow-shadow
          hover:translate-x-boxShadowX hover:translate-y-boxShadowY hover:shadow-none

noShadow: text-main-foreground bg-main border-2 border-border

neutral:  bg-secondary-background text-foreground border-2 border-border shadow-shadow
          hover:translate-x-boxShadowX hover:translate-y-boxShadowY hover:shadow-none

reverse:  text-main-foreground bg-main border-2 border-border
          hover:translate-x-reverseBoxShadowX hover:translate-y-reverseBoxShadowY hover:shadow-shadow

Sizes:
  default: h-10 px-4 py-2
  sm:      h-9 px-3
  lg:      h-11 px-8
  icon:    size-10
```

#### Card Component
```
Card:            rounded-base flex flex-col shadow-shadow border-2 gap-6 py-6
                 border-border bg-background text-foreground font-base

CardHeader:      @container/card-header grid auto-rows-min grid-rows-[auto_auto]
                 items-start gap-1.5 px-6

CardTitle:       font-heading leading-none

CardDescription: text-sm font-base

CardContent:     px-6

CardFooter:      flex items-center px-6
```

### Pure HTML/CSS Replication Guide

To replicate neobrutalism WITHOUT React, define these CSS custom properties and use Tailwind v4's @theme:

```css
/* In a <style type="text/tailwindcss"> block or CSS file */
@theme {
  --color-main: oklch(67.47% 0.1725 259.61);
  --color-bg: oklch(93.46% 0.0304 254.32);
  --color-bg2: oklch(100% 0 0);
  --color-fg: oklch(0% 0 0);
  --color-main-fg: oklch(0% 0 0);
  --color-border: oklch(0% 0 0);

  --radius-base: 5px;

  --shadow-neo: 4px 4px 0px 0px oklch(0% 0 0);

  --font-weight-heading: 700;
  --font-weight-base: 500;

  --spacing-shadow-x: 4px;
  --spacing-shadow-y: 4px;
}
```

Then in HTML:
```html
<!-- Neobrutalist Button -->
<button class="inline-flex items-center justify-center rounded-base text-sm
  bg-main text-main-fg border-2 border-border shadow-neo
  h-10 px-4 py-2 font-base transition-all
  hover:translate-x-shadow-x hover:translate-y-shadow-y hover:shadow-none">
  Click Me
</button>

<!-- Neobrutalist Card -->
<div class="rounded-base border-2 border-border shadow-neo bg-bg p-6 text-fg font-base">
  <h3 class="font-heading leading-none text-lg">Card Title</h3>
  <p class="text-sm mt-2">Card description text</p>
</div>
```

---

## 2. Tailwind CSS v4

### Version Info

| Detail | Value |
|--------|-------|
| Latest stable | **4.2.2** |
| Release date | March 2026 (4.2.2 latest) |
| Registry | npm |
| Package (CDN) | `@tailwindcss/browser@4` |
| Package (CLI) | `tailwindcss` + `@tailwindcss/cli` |

### CDN Usage (No Build Step)

```html
<!doctype html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
</head>
<body>
  <h1 class="text-3xl font-bold underline">Hello world!</h1>
</body>
</html>
```

**With custom theme (CDN):**
```html
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
<style type="text/tailwindcss">
  @theme {
    --color-clifford: #da373d;
  }
</style>
```

**Critical:** Use `type="text/tailwindcss"` for style blocks that contain Tailwind directives when using the CDN.

### Key Changes from v3 to v4

| Feature | v3 | v4 |
|---------|----|----|
| Config file | `tailwind.config.js` (JS) | `@theme` in CSS |
| Import syntax | `@tailwind base/components/utilities` | `@import "tailwindcss"` |
| Engine | Node.js | Rust (Oxide) — 3.8x faster |
| Content detection | Manual `content` array | Automatic scanning |
| Color format | hex/rgb | OKLCH preferred |
| Gradient utilities | `bg-gradient-to-*` | `bg-linear-to-*` |
| Custom variants | JS plugin | `@custom-variant` in CSS |
| Custom utilities | JS plugin | `@utility` in CSS |
| Plugins | JS imports in config | `@plugin "path"` in CSS |

### @theme Directive Reference

```css
@import "tailwindcss";

@theme {
  /* Colors — generates bg-*, text-*, border-* utilities */
  --color-primary: oklch(0.72 0.11 178);
  --color-accent: #ff6600;

  /* Font families */
  --font-sans: ui-sans-serif, system-ui, sans-serif;
  --font-mono: ui-monospace, monospace;

  /* Font weight — generates font-* utilities */
  --font-weight-bold: 700;
  --font-weight-medium: 500;

  /* Spacing — affects p-*, m-*, gap-*, etc. */
  --spacing: 0.25rem;  /* base unit */

  /* Border radius — generates rounded-* utilities */
  --radius-lg: 0.5rem;
  --radius-xl: 0.75rem;

  /* Shadows — generates shadow-* utilities */
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  --shadow-neo: 4px 4px 0px 0px #000;

  /* Container */
  --container-2xl: 1400px;
}
```

**@theme vs @theme inline:**
- `@theme` — Stores CSS variable values directly. Generates utility classes.
- `@theme inline` — Used when theme variables reference OTHER variables (`var(--something)`). The utility class uses the *value* instead of creating a reference chain. Prevents CSS variable scoping issues.

### CDN Limitations
- Development/prototyping only — not for production
- No tree-shaking (ships full ~140KB library)
- Cannot use `@plugin` for third-party plugins
- Limited customization compared to build step
- Browser support: Chrome 111+, Firefox 128+, Safari 16.4+

### Production Alternative for Pure HTML
```bash
# Install
npm install tailwindcss @tailwindcss/cli

# Create input.css
echo '@import "tailwindcss";' > input.css

# Build (with watch)
npx @tailwindcss/cli -i input.css -o styles.css --watch

# Build (minified for production)
npx @tailwindcss/cli -i input.css -o styles.css --minify
```

---

## 3. D3.js for Graph Visualization

### Version Info

| Detail | Value |
|--------|-------|
| Latest stable | **7.9.0** |
| Registry | npm |
| CDN (jsDelivr) | `https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js` |
| CDN (d3js.org) | `https://d3js.org/d3.v7.min.js` |
| CDN (Google) | `https://ajax.googleapis.com/ajax/libs/d3js/7.9.0/d3.min.js` |

### HTML Setup (Vanilla, No Framework)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>D3 Graph Visualization</title>
  <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
  <style>
    .node circle { fill: steelblue; stroke: #fff; stroke-width: 2px; cursor: pointer; }
    .link { stroke: #999; stroke-opacity: 0.6; }
    .tooltip {
      position: absolute; visibility: hidden;
      background: #fff; border: 2px solid #000;
      border-radius: 5px; padding: 10px;
      font-size: 14px; pointer-events: none;
    }
  </style>
</head>
<body>
  <svg id="graph" width="960" height="600"></svg>
  <div class="tooltip"></div>
  <script src="graph.js"></script>
</body>
</html>
```

### Force-Directed Graph Pattern

```javascript
// Data structure
const data = {
  nodes: [
    { id: "app", group: 1, label: "Application" },
    { id: "api", group: 2, label: "API Layer" },
    { id: "db", group: 3, label: "Database" },
  ],
  links: [
    { source: "app", target: "api" },
    { source: "api", target: "db" },
  ]
};

const width = 960, height = 600;
const svg = d3.select("#graph");

// Create a container group for zoom/pan
const g = svg.append("g");

// Force simulation
const simulation = d3.forceSimulation(data.nodes)
  .force("link", d3.forceLink(data.links).id(d => d.id).distance(100))
  .force("charge", d3.forceManyBody().strength(-300))
  .force("center", d3.forceCenter(width / 2, height / 2))
  .force("collide", d3.forceCollide().radius(20));

// Draw links
const link = g.append("g")
  .selectAll("line")
  .data(data.links)
  .join("line")
    .attr("class", "link")
    .attr("stroke-width", 2);

// Draw nodes
const node = g.append("g")
  .selectAll("circle")
  .data(data.nodes)
  .join("circle")
    .attr("r", 20)
    .attr("class", "node")
    .call(d3.drag()
      .on("start", dragstarted)
      .on("drag", dragged)
      .on("end", dragended));

// Update positions on each tick
simulation.on("tick", () => {
  link
    .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  node
    .attr("cx", d => d.x).attr("cy", d => d.y);
});

// Drag handlers
function dragstarted(event, d) {
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}
function dragged(event, d) {
  d.fx = event.x; d.fy = event.y;
}
function dragended(event, d) {
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}
```

### Zoom and Pan Pattern

```javascript
const zoom = d3.zoom()
  .scaleExtent([0.5, 5])    // min 0.5x, max 5x zoom
  .on("zoom", (event) => {
    g.attr("transform", event.transform);
  });

svg.call(zoom);

// Optional: Reset zoom button
document.getElementById("reset").addEventListener("click", () => {
  svg.transition().duration(750)
    .call(zoom.transform, d3.zoomIdentity);
});
```

### Tooltip Pattern

```javascript
const tooltip = d3.select(".tooltip");

node
  .on("mouseover", (event, d) => {
    tooltip
      .style("visibility", "visible")
      .html(`<strong>${d.label}</strong><br>Group: ${d.group}`);
  })
  .on("mousemove", (event) => {
    tooltip
      .style("top", (event.pageY - 10) + "px")
      .style("left", (event.pageX + 10) + "px");
  })
  .on("mouseout", () => {
    tooltip.style("visibility", "hidden");
  });
```

### Tree Layout Pattern (Hierarchical/Dependency Graphs)

```javascript
const treeData = {
  name: "Root",
  children: [
    { name: "Child A", children: [{ name: "Leaf 1" }, { name: "Leaf 2" }] },
    { name: "Child B", children: [{ name: "Leaf 3" }] }
  ]
};

const margin = { top: 20, right: 90, bottom: 30, left: 90 };
const width = 960 - margin.left - margin.right;
const height = 500 - margin.top - margin.bottom;

const svg = d3.select("body").append("svg")
  .attr("width", width + margin.left + margin.right)
  .attr("height", height + margin.top + margin.bottom)
  .append("g")
  .attr("transform", `translate(${margin.left},${margin.top})`);

const treemap = d3.tree().size([height, width]);
const root = d3.hierarchy(treeData, d => d.children);
root.x0 = height / 2;
root.y0 = 0;

function update(source) {
  const treeLayout = treemap(root);
  const nodes = treeLayout.descendants();
  const links = treeLayout.descendants().slice(1);

  // Normalize depth
  nodes.forEach(d => { d.y = d.depth * 180; });

  // Nodes
  const node = svg.selectAll("g.node")
    .data(nodes, d => d.id || (d.id = ++i));

  const nodeEnter = node.enter().append("g")
    .attr("class", "node")
    .attr("transform", d => `translate(${source.y0},${source.x0})`)
    .on("click", (event, d) => {
      d.children = d.children ? null : d._children; // Toggle collapse
      update(d);
    });

  nodeEnter.append("circle").attr("r", 10).attr("fill", "#fff").attr("stroke", "steelblue");
  nodeEnter.append("text").attr("dy", ".35em").text(d => d.data.name);

  // Links
  const link = svg.selectAll("path.link")
    .data(links, d => d.id);

  link.enter().append("path")
    .attr("class", "link")
    .attr("fill", "none")
    .attr("stroke", "#ccc")
    .attr("stroke-width", 2)
    .attr("d", d => {
      return `M ${d.y} ${d.x}
              C ${(d.y + d.parent.y) / 2} ${d.x},
                ${(d.y + d.parent.y) / 2} ${d.parent.x},
                ${d.parent.y} ${d.parent.x}`;
    });
}

let i = 0;
update(root);
```

### Performance Tips for Large Graphs
- **500+ nodes:** Use `requestAnimationFrame` throttling; update every 3 ticks
- **1000+ nodes:** Switch from SVG to Canvas rendering
- **Simulation tuning:** Adjust `alphaDecay(0.02)` for longer settling time
- **Force tuning:** `forceManyBody().strength(-50)` for less repulsion (denser graphs)

---

## 4. Pure HTML/CSS/JS Architecture (No Framework)

### Recommended Project Structure

```
project/
├── index.html              # Single HTML shell
├── styles.css              # Or use Tailwind via CDN
├── app.js                  # Entry point, router setup
├── router.js               # Client-side SPA router
├── components/             # Reusable UI pieces
│   ├── sidebar.js
│   ├── header.js
│   └── card.js
├── views/                  # Page-level views
│   ├── dashboard.js
│   ├── graph.js
│   └── settings.js
└── utils/
    └── state.js            # Simple state management
```

### Client-Side Routing (History API)

```javascript
// router.js
class Router {
  constructor() {
    this.routes = {};
    window.addEventListener("popstate", () => this.resolve());
  }

  add(path, handler) {
    this.routes[path] = handler;
    return this;
  }

  navigate(path) {
    window.history.pushState({}, "", path);
    this.resolve();
  }

  resolve() {
    const path = window.location.pathname;
    const handler = this.routes[path];
    if (handler) {
      handler();
    } else if (this.routes["*"]) {
      this.routes["*"]();
    }
  }
}

// Usage
const router = new Router();
router
  .add("/", () => renderView("dashboard"))
  .add("/graph", () => renderView("graph"))
  .add("/settings", () => renderView("settings"))
  .add("*", () => renderView("404"));

// Intercept link clicks
document.addEventListener("click", (e) => {
  const link = e.target.closest("[data-link]");
  if (link) {
    e.preventDefault();
    router.navigate(link.getAttribute("href"));
  }
});

router.resolve(); // Initial route
```

### View Rendering Pattern (Template Literals)

```javascript
// views/dashboard.js
export function dashboardView() {
  return `
    <div class="p-6">
      <h1 class="font-heading text-2xl mb-4">Dashboard</h1>
      <div class="grid grid-cols-3 gap-4">
        ${cardComponent({ title: "Agents", value: "42" })}
        ${cardComponent({ title: "Tasks", value: "128" })}
        ${cardComponent({ title: "Errors", value: "3" })}
      </div>
    </div>
  `;
}

// Render function
function renderView(viewName) {
  const content = document.getElementById("content");
  const views = { dashboard: dashboardView, graph: graphView, settings: settingsView };
  const viewFn = views[viewName];
  if (viewFn) {
    content.innerHTML = viewFn();
    // Re-attach event listeners after innerHTML update
    attachViewListeners(viewName);
  }
}
```

### Component Pattern (Template Functions)

```javascript
// components/card.js
function cardComponent({ title, value, description = "" }) {
  return `
    <div class="rounded-base border-2 border-border shadow-neo bg-bg p-6 font-base">
      <h3 class="font-heading leading-none text-lg">${title}</h3>
      <p class="text-3xl font-heading mt-2">${value}</p>
      ${description ? `<p class="text-sm mt-1 opacity-70">${description}</p>` : ""}
    </div>
  `;
}
```

### Sidebar Navigation Pattern

```html
<!-- index.html shell -->
<body class="bg-bg text-fg font-base">
  <div class="flex h-screen">
    <!-- Sidebar -->
    <aside id="sidebar" class="w-60 border-r-2 border-border bg-bg2 flex flex-col p-4 gap-2">
      <h2 class="font-heading text-xl mb-4 px-2">My App</h2>
      <a href="/" data-link
         class="px-3 py-2 rounded-base border-2 border-transparent
                hover:border-border hover:bg-main hover:text-main-fg
                transition-all font-base text-sm">
        Dashboard
      </a>
      <a href="/graph" data-link
         class="px-3 py-2 rounded-base border-2 border-transparent
                hover:border-border hover:bg-main hover:text-main-fg
                transition-all font-base text-sm">
        Graph View
      </a>
      <a href="/settings" data-link
         class="px-3 py-2 rounded-base border-2 border-transparent
                hover:border-border hover:bg-main hover:text-main-fg
                transition-all font-base text-sm">
        Settings
      </a>
    </aside>

    <!-- Main Content -->
    <main id="content" class="flex-1 overflow-auto p-6">
      <!-- Views render here -->
    </main>
  </div>

  <script type="module" src="app.js"></script>
</body>
```

### Simple State Management (Observer Pattern)

```javascript
// utils/state.js
class Store {
  constructor(initialState = {}) {
    this.state = initialState;
    this.listeners = [];
  }

  getState() {
    return { ...this.state };
  }

  setState(updates) {
    this.state = { ...this.state, ...updates };
    this.listeners.forEach(fn => fn(this.state));
  }

  subscribe(fn) {
    this.listeners.push(fn);
    return () => {
      this.listeners = this.listeners.filter(l => l !== fn);
    };
  }
}

// Global store
const store = new Store({
  currentView: "dashboard",
  graphData: null,
  theme: "light",
});
```

### Web Components Alternative (Native Browser API)

```javascript
// components/neo-card.js
class NeoCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    const title = this.getAttribute("title") || "";
    const value = this.getAttribute("value") || "";
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          border: 2px solid black;
          border-radius: 5px;
          box-shadow: 4px 4px 0px 0px black;
          padding: 1.5rem;
          background: white;
          font-family: inherit;
        }
        h3 { font-weight: 700; margin: 0; }
        .value { font-size: 1.875rem; font-weight: 700; margin-top: 0.5rem; }
      </style>
      <h3>${title}</h3>
      <div class="value">${value}</div>
    `;
  }
}

customElements.define("neo-card", NeoCard);
// Usage: <neo-card title="Agents" value="42"></neo-card>
```

**Recommendation:** For a Tailwind-heavy project, use the **template literal approach** (not Web Components), since Shadow DOM prevents Tailwind utility classes from reaching inner elements. Web Components with Shadow DOM require their own scoped styles, which conflicts with utility-first CSS.

### Best Practices for Multi-View SPA
1. **Use ES Modules** (`type="module"`) for clean imports
2. **Lazy load views** with dynamic `import()` — only load view code when navigated to
3. **Event delegation** — attach listeners to parent containers, not individual elements
4. **Clean up** — remove event listeners and cancel intervals when switching views
5. **URL-driven state** — derive application state from the URL, not the other way around

---

## Dependencies Summary

| Package | Version | Registry | CDN URL | Notes |
|---------|---------|----------|---------|-------|
| Tailwind CSS | 4.2.2 | npm | `https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4` | CDN for dev only |
| D3.js | 7.9.0 | npm | `https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js` | Stable, no major changes expected |
| neobrutalism-components | N/A | GitHub | N/A | Design tokens only — no runtime dependency |

## Sources

1. https://github.com/ekmas/neobrutalism-components — Source repo, globals.css, button.tsx, card.tsx
2. https://tailwindcss.com/docs/installation/play-cdn — Official Tailwind v4 CDN docs
3. https://tailwindcss.com/docs/theme — Official @theme directive docs
4. https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js — D3.js CDN (jsDelivr)
5. https://d3js.org — Official D3.js site
6. https://observablehq.com/@d3/collapsible-tree — D3 tree layout examples
7. https://d3-graph-gallery.com/graph/interactivity_tooltip.html — D3 tooltip patterns
8. https://neubrutalism.com — Neubrutalism design reference
9. https://lobehub.com/skills/curiositech-windags-skills-neobrutalist-web-designer/ — Neobrutalism design system guide
10. https://jschof.dev/posts/2025/11/build-your-own-router/ — Vanilla JS SPA router with URLPattern
11. https://frontendmasters.com/courses/vanilla-js-go/ — Frontend Masters vanilla JS SPA course
12. https://jsgurujobs.com/blog/vanilla-javascript-web-components-beat-react-the-framework-free-future-of-2026 — Web Components 2026 analysis
