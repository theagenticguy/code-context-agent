# Deterministic Indexer

The `index` command builds a code graph deterministically without any LLM invocations. It is faster and cheaper than full analysis, producing a `code_graph.json` that can be immediately queried via the MCP server.

## Usage

```bash
# Index the current directory
code-context-agent index .

# Index a specific repository
code-context-agent index /path/to/repo

# Custom output directory
code-context-agent index . --output-dir ./output

# Quiet mode
code-context-agent index . --quiet
```

## Pipeline

The indexer runs a fixed seven-step pipeline:

| Step | Source | What It Produces |
|------|--------|-----------------|
| 1. File manifest | ripgrep (`rg --files`) | List of all tracked files |
| 2. Language detection | File extensions | Files grouped by language (py, ts, rust, go, java) |
| 3. LSP symbols | ty, typescript-language-server, etc. | Function, class, method nodes + containment edges |
| 4. AST-grep patterns | Rule packs per language | Business logic pattern_match nodes (db, auth, http, etc.) |
| 5. Git hotspots | `git log` analysis | FILE nodes with churn metadata + COCHANGES edges |
| 6. Clone detection | jscpd via npx | SIMILAR_TO edges between duplicate code blocks |
| 7. Save graph | JSON serialization | `.code-context/code_graph.json` |

## Graceful Degradation

Each step operates independently. If a tool is missing (e.g., `ast-grep` not installed, LSP server fails to start), that step is skipped and indexing continues with the remaining tools. The final graph contains whatever data was successfully collected.

## When to Use

| Scenario | Command |
|----------|---------|
| Quick graph for MCP queries | `code-context-agent index .` |
| Full narrated analysis with AI | `code-context-agent analyze .` |
| CI pipeline pre-indexing | `code-context-agent index . --quiet` |
| Re-index after code changes | `code-context-agent index .` (overwrites existing) |

The `index` command produces only `code_graph.json`. It does not generate `CONTEXT.md`, signatures, bundles, or the structured `AnalysisResult`. For those artifacts, use `analyze`.

## Output

The graph is saved to `.code-context/code_graph.json` (or `<output-dir>/code_graph.json`). After indexing, you can:

- Start the MCP server: `code-context-agent serve`
- Query the graph: `query_code_graph(repo_path, algorithm="hotspots")`
- Explore interactively: `explore_code_graph(repo_path, action="overview")`
- Visualize: `code-context-agent viz .`

## Language Support

| Language | Extension | LSP Server | AST-grep Rules |
|----------|-----------|------------|----------------|
| Python | `.py` | ty, pyright | `py_business_logic`, `py_code_smells` |
| TypeScript/JavaScript | `.ts`, `.tsx`, `.js`, `.jsx` | typescript-language-server | `ts_business_logic`, `ts_code_smells` |
| Rust | `.rs` | rust-analyzer | -- |
| Go | `.go` | gopls | -- |
| Java | `.java` | jdtls | -- |
