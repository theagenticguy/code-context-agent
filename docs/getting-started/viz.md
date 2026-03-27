# Web Visualization

The `viz` command launches an interactive multi-view web visualization of analysis results.

## Usage

```bash
# Visualize the current directory (requires prior analysis)
code-context-agent viz .

# Specify a different repository
code-context-agent viz /path/to/repo

# Custom port
code-context-agent viz . --port 9000

# Don't auto-open browser
code-context-agent viz . --no-open

```

## Views

The default visualizer provides 10 specialized views:

- **Landing** -- Entry point with file drop zone, demo data loader, and keyboard shortcuts
- **Dashboard** -- Overview statistics, node/edge distributions, health gauge, risk list
- **Graph** -- Interactive D3.js force-directed graph with search, filters, and detail panel
- **Modules** -- D3 circle packing with drill-down module exploration
- **Hotspots** -- Betweenness centrality rankings, entry points, distribution charts
- **Dependencies** -- Search-driven tree layout with upstream/downstream toggle and depth controls
- **Narrative** -- CONTEXT.md rendered as markdown with TOC and scroll-spy
- **Bundles** -- CONTEXT.bundle.md source bundle explorer
- **Insights** -- Refactoring candidates, code health scores, phase timings
- **Signatures** -- CONTEXT.signatures.md with search functionality

Navigate between views using the sidebar or keyboard shortcuts (keys 1-9, 0). Press `d` to toggle dark mode.

## Prerequisites

The `viz` command requires a prior `analyze` or `index` run to generate the `.code-context/` output directory. At minimum, `code_graph.json` should exist for the graph visualization.

## Data Loading

The visualizer supports three data loading methods:

1. **Server mode** -- when launched via `code-context-agent viz .`, data is served from the `.code-context/` directory
2. **Drag and drop** -- drop `code_graph.json`, `analysis_result.json`, or context files onto the landing page
3. **Demo data** -- click "Load Demo" on the landing page for a sample dataset

## Architecture

The viz command starts a local HTTP server that serves:

- Static files from the `code_context_agent/ui/` package directory (HTML, CSS, JavaScript)
- `/data/*` requests proxied to the `.code-context/` output directory
- `/api/graph` endpoint serving `code_graph.json`
- `/api/stats` endpoint serving graph statistics via `CodeGraph.describe()`

The frontend is a zero-build single-page application (26 files, ~6,000 lines) using vanilla JavaScript modules with Tailwind CSS v4 (CDN) and D3.js v7 (CDN).

| Module | Purpose |
|--------|---------|
| `app.js` | Router, view lifecycle, keyboard shortcuts |
| `store.js` | Shared application state |
| `data-loader.js` | Data loading, drag-and-drop, demo data |
| `graph-utils.js` | Shared graph computation utilities |
| `views/*.js` | 10 view modules (one per view) |
| `components/*.js` | 7 shared UI components |

## Data Files

The visualizer reads these files from `.code-context/`:

| File | Used For |
|------|----------|
| `code_graph.json` | Graph structure (nodes, edges, metadata) |
| `CONTEXT.md` | Narrative view |
| `CONTEXT.bundle.md` | Bundles view |
| `CONTEXT.signatures.md` | Signatures view |
| `analysis_result.json` | Dashboard statistics, insights |

