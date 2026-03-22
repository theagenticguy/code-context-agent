# Quick Start

## Basic Usage

```bash
# Analyze current directory
code-context-agent analyze .

# Analyze specific repository
code-context-agent analyze /path/to/repo

# Focus on specific area
code-context-agent analyze . --focus "authentication system"

# Custom output directory
code-context-agent analyze . --output-dir ./analysis

# Only analyze changes since a date or ref
code-context-agent analyze . --since "2025-01-01"

# JSON output format (for programmatic consumption)
code-context-agent analyze . --output-format json

# Quiet mode (suppress Rich TUI)
code-context-agent analyze . --quiet

# Debug mode (verbose logging)
code-context-agent analyze . --debug

# Exhaustive analysis (no size limits, all algorithms)
code-context-agent analyze . --full

# Verify external tool dependencies
code-context-agent check
```

The agent automatically determines analysis depth based on repository size and complexity. Use `--full` for exhaustive analysis with no size limits.

## What Happens During Analysis

1. **File manifest** -- The agent creates a complete inventory of the repository using ripgrep
2. **Orientation** -- repomix generates a token distribution tree showing project structure
3. **Signal gathering** -- Multiple tools run in parallel:
    - LSP: semantic analysis (definitions, references, symbols)
    - ast-grep: structural pattern matching against rule packs
    - Git: hotspots, coupling, churn, blame analysis
    - Graph: NetworkX dependency graph with centrality/PageRank metrics
4. **Ranking** -- Files are scored across all signal layers
5. **Bundling** -- Top-ranked files are bundled with Tree-sitter compression
6. **Output** -- Structured `AnalysisResult` written as narrated markdown to `.code-context/`

## Output Files

All outputs land in `.code-context/` (or your custom `--output-dir`):

| File | Description |
|------|-------------|
| `CONTEXT.md` | Main narrated context (<=300 lines in standard mode) |
| `CONTEXT.orientation.md` | Token distribution tree |
| `CONTEXT.bundle.md` | Bundled source code (compressed) |
| `CONTEXT.signatures.md` | Signatures-only structural view |
| `files.all.txt` | Complete file manifest |
| `files.business.txt` | Curated business logic files |
| `code_graph.json` | Persisted graph data |
| `FILE_INDEX.md` | File index with graph metrics (complex repos) |
| `analysis_result.json` | Structured analysis result (Pydantic JSON) |
| `CONTEXT.modules/` | Per-module context files (full mode only) |
| `CONTEXT.business.*.md` | Category-specific business logic files |

## Using the Output

The `.code-context/` directory is designed for consumption by AI coding assistants. Point your assistant at `CONTEXT.md` as the entry point:

```bash
# Example: feed context to another agent
cat .code-context/CONTEXT.md | your-ai-assistant
```

The narrated context includes architecture diagrams, ranked file tables, risk assessments, and business logic summaries -- all formatted for machine parsing (tables over prose, typed schemas, bounded diagrams).

## Quick Indexing (No LLM)

For a fast, cheap graph without AI narration:

```bash
# Build a code graph deterministically
code-context-agent index .

# Then query it via MCP or visualize it
code-context-agent serve
code-context-agent viz .
```

See the [Deterministic Indexer documentation](../tools/indexer.md) for details.

## Visualization

After analysis or indexing, launch an interactive web UI:

```bash
code-context-agent viz .
code-context-agent viz . --port 9000
```

This opens a D3.js force-directed graph visualization with hotspot highlighting, module coloring, dependency chains, and the CONTEXT.md narrative. See the [Visualization guide](viz.md) for details.

## MCP Server

After analysis, you can expose the results to coding agents via MCP:

=== "stdio (Claude Code / Claude Desktop)"

    ```bash
    code-context-agent serve
    ```

=== "HTTP (networked access)"

    ```bash
    code-context-agent serve --transport http --port 8000
    ```

The MCP server provides tools for querying the code graph (`query_code_graph`), progressive exploration (`explore_code_graph`), graph statistics (`get_graph_stats`), diff impact analysis (`diff_impact`), multi-repo discovery (`list_repos`), Cypher queries (`execute_cypher`), and kicking off new analyses (`start_analysis`). It also exposes the analysis artifacts as MCP resources.

See the [MCP Server documentation](../tools/mcp.md) for full details and client configuration.
