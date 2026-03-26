# FAQ

Frequently asked questions about code-context-agent.

---

### How much does analysis cost?

Token consumption depends on the analysis mode and codebase size:

| Mode | Input tokens | Output tokens |
|------|-------------|---------------|
| Standard | 50K--200K | 10K--30K |
| Full | 200K--500K | 30K--50K |
| Index only (`index` command) | 0 | 0 |

The `index` command makes zero LLM calls -- it builds the code graph entirely with deterministic tools (LSP, AST-grep, git, framework detection). Cost depends on your Amazon Bedrock pricing tier (on-demand vs. provisioned throughput).

!!! tip
    Run `code-context-agent index .` first (free). The `analyze` command loads the pre-built graph automatically, reducing the token budget spent on structural discovery.

---

### Is it safe to run on my codebase?

Yes. The agent operates under strict security constraints:

- **Read-only filesystem access** -- the agent cannot modify your source code.
- **Shell allowlist** -- the `shell` tool enforces a read-only program allowlist. Destructive commands (`rm`, `mv`, `curl`, `wget`, etc.) and shell operators (`|`, `;`, `&&`, `>`, etc.) are blocked.
- **Input validation** -- all tool inputs are validated for path traversal (`..`) and injection attacks.
- **No external data exfiltration** -- data is sent only to Amazon Bedrock for LLM inference. Nothing is sent to third-party services (context7 runs locally via `npx`).
- **Scoped output** -- all output files are written exclusively to `.code-context/` (or your custom `--output-dir`).

See the [Security](security/overview.md) page for full details on shell hardening, input validation, and CI security scanning.

---

### Why Claude Opus 4.6 specifically?

Opus 4.6 is selected as the default for several reasons:

- **Complex multi-tool reasoning** -- the analysis pipeline involves 49 tools across 4 specialist agents. Opus-class models handle long tool chains and cross-signal synthesis more reliably.
- **Adaptive thinking (extended reasoning)** -- improves architectural analysis quality by allowing the model to reason through ambiguous structural patterns.
- **1M context window** -- via `anthropic_beta: context-1m-2025-08-07`, the model can process large codebases without truncation.
- **Cross-region inference** -- the `global.` prefix in the default model ID (`global.anthropic.claude-opus-4-6-v1`) provides best availability across AWS regions.

---

### Can I use a different model?

Yes. Set the `CODE_CONTEXT_MODEL_ID` environment variable to any Bedrock model ID:

```bash
export CODE_CONTEXT_MODEL_ID=us.anthropic.claude-sonnet-4-20250514-v1:0
```

!!! warning
    Models without adaptive thinking support require `CODE_CONTEXT_TEMPERATURE` to be set below 1.0 (temperature 1.0 is required specifically for thinking-enabled models). The system prompts and tool descriptions are optimized for Opus-class models -- results may vary with smaller models.

---

### Does it work with monorepos?

Yes, but large monorepos (more than 10,000 files) benefit from these strategies:

1. **Scope with `--focus`** to analyze a specific area:
    ```bash
    code-context-agent analyze . --focus "payments service"
    ```

2. **Use the KuzuDB backend** for persistent, disk-backed graph storage:
    ```bash
    export CODE_CONTEXT_GRAPH_BACKEND=kuzu
    ```

3. **Pre-index** to separate the (free) graph-building step from the (token-consuming) analysis step:
    ```bash
    code-context-agent index .
    code-context-agent analyze .
    ```

4. **Adjust LSP file limits** if the monorepo has many files:
    ```bash
    export CODE_CONTEXT_LSP_MAX_FILES=20000
    ```

---

### What languages are supported?

The analysis is **language-agnostic** at the core level. Ripgrep, AST-grep, git history, and framework detection work with any programming language.

**LSP integration** provides deeper semantic analysis (definitions, references, hover docs) for languages with configured servers:

| Language | Default LSP servers |
|----------|-------------------|
| Python | `ty server`, `pyright-langserver --stdio` |
| TypeScript / JavaScript | `typescript-language-server --stdio` |
| Rust | `rust-analyzer` |
| Go | `gopls serve` |
| Java | `jdtls` |

**Framework detection** covers: Next.js, Express, Django, Flask, FastAPI, pytest, CLI frameworks, and more (8 framework patterns total).

To add a new language, extend `CODE_CONTEXT_LSP_SERVERS` with its key and an ordered list of server commands:

```bash
export CODE_CONTEXT_LSP_SERVERS='{"py": ["ty server"], "ts": ["typescript-language-server --stdio"], "rb": ["solargraph stdio"]}'
```

---

### What is the MCP server for?

The MCP (Model Context Protocol) server exposes code-context-agent's unique capabilities to AI coding assistants like Claude Code, Claude Desktop, and Cursor.

Through the MCP server, an AI assistant can:

- **Start and poll analysis** (`start_analysis`, `check_analysis`)
- **Query the code graph** with 12 graph algorithms including blast radius, flow analysis, and diff impact (`query_code_graph`)
- **Explore the graph progressively** with guided next-step hints (`explore_code_graph`)
- **Run Cypher queries** against the graph (`execute_cypher`)
- **List registered repos** across the multi-repo registry (`list_repos`)

Start the server:

```bash
# stdio transport (for Claude Code / Claude Desktop)
code-context-agent serve

# HTTP transport (for networked clients)
code-context-agent serve --transport http --port 8000
```

See the [MCP Server](tools/mcp.md) documentation for full setup and tool reference.

---

### What's the difference between `analyze` and `index`?

| | `index` | `analyze` |
|---|---------|-----------|
| **What it does** | Builds a structural code graph | Full LLM-driven codebase analysis |
| **Time** | ~30 seconds | ~5--10 minutes (standard), ~30--60 minutes (full) |
| **LLM calls** | None (deterministic) | Yes (Swarm of 4 specialist agents) |
| **Cost** | Free | Token-based (see cost FAQ above) |
| **Output** | `code_graph.json` | `CONTEXT.md`, `CONTEXT.bundle.md`, `analysis_result.json`, `code_graph.json` |
| **Uses** | LSP, AST-grep, git, framework detection | All index tools + LLM reasoning + ripgrep + repomix |

**Best practice**: Run `index` first, then `analyze`. The analysis agent loads the pre-built graph from `.code-context/code_graph.json`, which saves significant time and tokens on structural discovery.

```bash
code-context-agent index /path/to/repo
code-context-agent analyze /path/to/repo
```

---

### What output files should I use?

After running `analyze`, the `.code-context/` directory contains:

| File | Best for |
|------|----------|
| `CONTEXT.md` | Feeding to AI coding assistants as context. This is the narrated architecture document. |
| `CONTEXT.bundle.md` | Compressed source code bundle (via repomix Tree-sitter compression). Useful as supplementary context. |
| `analysis_result.json` | Programmatic consumption. Contains the structured `AnalysisResult` with business logic items, architectural risks, and module metadata. |
| `code_graph.json` | Graph queries via the MCP server or the `viz` command. Contains the full node-link graph. |

For **full mode** (`--full`), additional files are produced:

| File | Best for |
|------|----------|
| `CONTEXT.modules/<module>.md` | Per-module context documents for scoped AI assistance |
| `FILE_INDEX.md` | Comprehensive file index with centrality, PageRank, and churn metrics |
| `CONTEXT.business.<category>.md` | Category-specific business logic documents |

To explore the graph interactively:

```bash
code-context-agent viz .
```

---

### How do I run incremental analysis?

Use `--since` to analyze only files changed since a git ref:

```bash
# Changes since the last 5 commits
code-context-agent analyze . --since HEAD~5

# Changes since a branch point
code-context-agent analyze . --since main
```

Incremental analysis is faster and cheaper than a full re-analysis. It works best when a prior `.code-context/` output already exists, as the agent can reference the existing graph and context.

!!! note
    `--since` and `--full` cannot be combined. Incremental analysis is scoped by definition, while full mode is exhaustive.

---

### How do I analyze a specific area of a codebase?

Use `--focus` to direct the analysis toward a specific subsystem or concern:

```bash
code-context-agent analyze . --focus "authentication and authorization"
code-context-agent analyze . --focus "database layer"
code-context-agent analyze . --focus "API endpoints"
```

The focus string is passed to the LLM agents, which prioritize exploring files, symbols, and patterns related to that area. The code graph and git history analysis are still performed on the full repository, but the narrative output concentrates on the focused area.

`--focus` can be combined with `--full` for exhaustive analysis scoped to a specific area:

```bash
code-context-agent analyze . --full --focus "payments"
```
