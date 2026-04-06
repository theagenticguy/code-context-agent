# Troubleshooting

This page covers common issues encountered when using code-context-agent and their solutions.

---

## Common Issues

### "External tool not found" errors

Run the built-in dependency checker to see which tools are missing:

```bash
code-context-agent check
```

The checker verifies: **ripgrep** (`rg`), **ast-grep**, **repomix**, and **npx**.

| Tool | Required? | Install |
|------|-----------|---------|
| `rg` (ripgrep) | Yes | `cargo install ripgrep` |
| `ast-grep` | Yes | `cargo install ast-grep` |
| `repomix` | Optional | `npm install -g repomix` |
| `npx` (Node.js) | Optional | Install [Node.js](https://nodejs.org/) |
| `typescript-language-server` | Optional | `npm install -g typescript-language-server` |
| `ty` | Optional | `uv tool install ty` |

!!! tip
    `ripgrep` and `ast-grep` are required for core analysis functionality. The other tools enhance analysis quality but the agent compensates when they are absent.

For full installation details, see the [Installation](getting-started/installation.md) guide.

---

### LSP server fails to start

**Symptoms**: "Failed to start LSP server" in logs, or LSP-based tools return empty results.

The agent compensates for LSP failures by falling back to AST-grep and ripgrep search (Tenet 6: Fail loud, fill gaps), so analysis still produces useful results even without LSP.

??? info "Checklist"

    1. **Is the language server installed?**
        - Python: `uv tool install ty` (primary) or `pip install pyright` (fallback)
        - TypeScript: `npm install -g typescript-language-server`
        - Rust: Install `rust-analyzer` via rustup or your package manager
        - Go: `go install golang.org/x/tools/gopls@latest`
        - Java: Install Eclipse JDT Language Server (`jdtls`)

    2. **Is the server on your PATH?**
        - Run the server command directly (e.g., `ty server`, `typescript-language-server --stdio`) to verify it starts.

    3. **Override LSP servers via environment variable**
        - Set `CODE_CONTEXT_LSP_SERVERS` to a JSON object mapping language keys to ordered fallback chains:
        ```bash
        export CODE_CONTEXT_LSP_SERVERS='{"py": ["pyright-langserver --stdio"], "ts": ["typescript-language-server --stdio"]}'
        ```

    4. **Increase startup timeout**
        - Default: 30 seconds. Maximum: 120 seconds.
        ```bash
        export CODE_CONTEXT_LSP_STARTUP_TIMEOUT=60
        ```

    5. **Increase operation timeout**
        - Default: 30 seconds. Maximum: 300 seconds.
        ```bash
        export CODE_CONTEXT_LSP_TIMEOUT=60
        ```

The default LSP fallback chains are:

| Language | Fallback chain |
|----------|---------------|
| Python | `ty server` -> `pyright-langserver --stdio` |
| TypeScript | `typescript-language-server --stdio` |
| Rust | `rust-analyzer` |
| Go | `gopls serve` |
| Java | `jdtls` |

---

### Analysis times out

**Symptoms**: Analysis exits with "stopped" status and an "exceeded limit" message.

Default timeouts:

| Mode | Default | Env variable | Range |
|------|---------|-------------|-------|
| Standard | 1200s (20 min) | `CODE_CONTEXT_AGENT_MAX_DURATION` | 60--7200s |
| Full | 3600s (60 min) | `CODE_CONTEXT_FULL_MAX_DURATION` | 300--14400s |

**Solutions**:

```bash
# Increase standard mode timeout to 40 minutes
export CODE_CONTEXT_AGENT_MAX_DURATION=2400

# Increase full mode timeout to 2 hours
export CODE_CONTEXT_FULL_MAX_DURATION=7200
```

!!! tip
    Run `code-context-agent index .` first. The pre-built code graph is loaded automatically during analysis, which significantly reduces the time the agent spends on structural discovery.

You can also increase the turn limits if the agent is making progress but running out of turns:

```bash
# Standard mode (default: 1000, max: 5000)
export CODE_CONTEXT_AGENT_MAX_TURNS=2000

# Full mode (default: 3000, max: 10000)
export CODE_CONTEXT_FULL_MAX_TURNS=5000
```

---

### "FullModeToolError" halts analysis

This error only occurs in `--full` mode and is intentional. The `FailFastHook` monitors every tool invocation and raises `FullModeToolError` when a non-exempt tool returns an error. This prevents silently degraded results.

**What it means**: A tool that the agent depends on for complete analysis returned an error.

**Solutions**:

1. **Fix the underlying tool issue** -- the error message identifies which tool failed and why. Common causes are missing dependencies or misconfigured LSP servers.
2. **Run `code-context-agent check`** to identify missing external tools.
3. **Use standard mode** (without `--full`) if you want graceful degradation instead of fail-fast behavior.

??? info "Exempt tools (allowed to fail in full mode)"

    The following tools are exempt from fail-fast and will not halt analysis:

    | Tool | Reason |
    |------|--------|
    | `rg_search` | Search misses are expected |
    | `context7_resolve-library-id` | External service, best-effort |
    | `context7_query-docs` | External service, best-effort |
    | `shell` | Exploratory commands may fail |
    | `gitnexus_*` | External MCP service, best-effort |

See [Full Mode](getting-started/full-mode.md) for complete details on exhaustive analysis behavior.

---

### Large repository memory issues

**Symptoms**: Out of memory errors, very slow graph operations, or the process being killed by the OS.

For repositories with more than 10,000 files, static analysis tools and GitNexus indexing can be slow.

**Solutions**:

1. **Use `--focus` to scope analysis** to a specific area of the codebase:

    ```bash
    code-context-agent analyze . --focus "payments module"
    ```

2. **Pre-index with `index`** so that the coordinator starts with a heuristic summary rather than running the full pipeline:

    ```bash
    code-context-agent index .
    code-context-agent analyze .
    ```

---

### AWS / Bedrock authentication errors

**Symptoms**: "Unable to locate credentials", "AccessDeniedException", or "ExpiredTokenException".

??? info "Checklist"

    1. **Verify AWS credentials**:
        ```bash
        aws sts get-caller-identity
        ```

    2. **Check region** -- the default is `us-east-1`:
        ```bash
        export CODE_CONTEXT_REGION=us-east-1
        ```

    3. **Ensure model access** -- Claude Opus 4.6 must be enabled in your Amazon Bedrock console for the configured region.

    4. **Cross-region inference** -- the default model ID (`global.anthropic.claude-opus-4-6-v1`) uses the `global.` prefix for cross-region inference. This requires cross-region inference to be enabled in your Bedrock settings.

    5. **Profile configuration** -- if using named profiles:
        ```bash
        export AWS_PROFILE=your-profile
        ```

---

### context7 MCP server issues

**Symptoms**: "Failed to start context7 MCP server" in logs.

The context7 integration requires `npx` (Node.js) to be available on the system. The agent launches the context7 MCP server as a subprocess via `npx`.

**Solutions**:

- **Install Node.js** to make `npx` available.
- **Disable context7** if you don't need library documentation lookups:
    ```bash
    export CODE_CONTEXT_CONTEXT7_ENABLED=false
    ```

!!! note
    The agent compensates if context7 is unavailable. Library documentation lookup enhances analysis quality but is not required for core functionality.

---

### Visualization won't load

**Symptoms**: Browser shows an empty page or an error when running `code-context-agent viz`.

??? info "Checklist"

    1. **Ensure prior analysis or indexing** -- the `viz` command requires `.code-context/` output:
        ```bash
        code-context-agent index .   # Quick: builds code graph only
        code-context-agent viz .
        ```

    2. **Check that analysis artifacts exist**:
        ```bash
        ls .code-context/heuristic_summary.json
        ```

    3. **Port conflict** -- the default port is 8765. Change it if occupied:
        ```bash
        code-context-agent viz . --port 9000
        ```

    4. **Prevent auto-open** -- use `--no-open` if your environment does not support browser auto-launch:
        ```bash
        code-context-agent viz . --no-open
        ```
        Then manually open the URL printed to the console.

---

## Debugging

### Enable debug logging

Debug mode disables the Rich TUI and enables verbose loguru output:

```bash
code-context-agent analyze . --debug
```

This shows detailed logs for every tool call, LSP interaction, graph operation, and hook execution.

### JSON output for CI/CD

Use `--quiet` to suppress all TUI output and emit only structured JSON log lines:

```bash
code-context-agent analyze . --quiet
```

Or use `--output-format json` to get the `AnalysisResult` as JSON on stdout:

```bash
code-context-agent analyze . --output-format json
```

### Preflight check

Run the full dependency check before analysis to surface issues early:

```bash
code-context-agent check
```
