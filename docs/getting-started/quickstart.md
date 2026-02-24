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

# Quiet mode (suppress Rich TUI)
code-context-agent analyze . --quiet

# Debug mode (verbose logging)
code-context-agent analyze . --debug
```

The agent automatically determines analysis depth based on repository size and complexity. No mode flags needed.

## What Happens During Analysis

1. **File manifest** --- The agent creates a complete inventory of the repository using ripgrep
2. **Orientation** --- repomix generates a token distribution tree showing project structure
3. **Signal gathering** --- Multiple tools run in parallel:
    - LSP: semantic analysis (definitions, references, symbols)
    - ast-grep: structural pattern matching against rule packs
    - Git: hotspots, coupling, churn, blame analysis
    - Graph: NetworkX dependency graph with centrality/PageRank metrics
4. **Ranking** --- Files are scored across all signal layers
5. **Bundling** --- Top-ranked files are bundled with Tree-sitter compression
6. **Output** --- Structured `AnalysisResult` written as narrated markdown to `.agent/`

## Output Files

All outputs land in `.agent/` (or your custom `--output-dir`):

| File | Description |
|------|-------------|
| `CONTEXT.md` | Main narrated context (<=300 lines) |
| `CONTEXT.orientation.md` | Token distribution tree |
| `CONTEXT.bundle.md` | Bundled source code (compressed) |
| `CONTEXT.signatures.md` | Signatures-only structural view |
| `files.all.txt` | Complete file manifest |
| `files.business.txt` | Curated business logic files |
| `code_graph.json` | Persisted graph data |
| `FILE_INDEX.md` | File index with graph metrics (complex repos) |

## Using the Output

The `.agent/` directory is designed for consumption by AI coding assistants. Point your assistant at `CONTEXT.md` as the entry point:

```bash
# Example: feed context to another agent
cat .agent/CONTEXT.md | your-ai-assistant
```

The narrated context includes architecture diagrams, ranked file tables, risk assessments, and business logic summaries --- all formatted for machine parsing (tables over prose, typed schemas, bounded diagrams).
