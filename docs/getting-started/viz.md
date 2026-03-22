# Web Visualization

The `viz` command launches an interactive web-based visualization of analysis results using D3.js force-directed graph rendering.

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

## Prerequisites

The `viz` command requires a prior `analyze` or `index` run to generate the `.code-context/` output directory. At minimum, `code_graph.json` should exist for the graph visualization.

## Features

The web UI provides several views:

### Force-Directed Graph

Interactive graph visualization where nodes are code elements (functions, classes, methods) and edges represent relationships (calls, imports, references, inherits). Nodes are colored by module (from Louvain community detection) and sized by degree.

### Hotspots Panel

Displays the top hotspot nodes ranked by betweenness centrality. Click a hotspot to center the graph on that node.

### Modules Panel

Shows detected modules with member counts and cohesion metrics. Expand a module to see its key nodes and internal structure.

### Dependencies Panel

Select a node to see its dependency chain -- what it depends on (outgoing) and what depends on it (incoming).

### Narrative Panel

Renders the `CONTEXT.md` narrative architecture document alongside the graph for reference.

## Architecture

The viz command starts a local HTTP server that serves:

- Static files from the `viz/` package directory (HTML, CSS, JavaScript)
- `/data/*` requests proxied to the `.code-context/` output directory
- `/api/graph` endpoint serving `code_graph.json`
- `/api/stats` endpoint serving graph statistics via `CodeGraph.describe()`

The frontend is a single-page application using vanilla JavaScript modules:

| Module | Purpose |
|--------|---------|
| `main.js` | Application entry point, data loading |
| `state.js` | Shared application state |
| `graph.js` | D3.js force simulation and SVG rendering |
| `hotspots.js` | Hotspot panel rendering |
| `modules.js` | Module panel rendering |
| `dependencies.js` | Dependency chain visualization |
| `narrative.js` | CONTEXT.md markdown rendering |
| `dashboard.js` | Stats dashboard and overview |

## Data Files

The visualizer reads these files from `.code-context/`:

| File | Used For |
|------|----------|
| `code_graph.json` | Graph structure (nodes, edges, metadata) |
| `CONTEXT.md` | Narrative panel |
| `analysis_result.json` | Dashboard statistics |
