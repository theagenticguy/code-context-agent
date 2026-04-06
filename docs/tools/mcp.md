# MCP Server

The MCP server exposes code-context-agent's core differentiators via the [Model Context Protocol](https://modelcontextprotocol.io), enabling coding agents (Claude Code, Cursor, etc.) to use analysis capabilities directly.

The server focuses on capabilities that complement GitNexus (structural code intelligence): multi-agent narrative analysis, git evolution data, static scan findings, risk-based review routing, and change verdicts for CI/CD integration.

## Starting the Server

=== "stdio (default)"

    ```bash
    code-context-agent serve
    ```

    Used for local MCP clients like Claude Code and Claude Desktop.

=== "HTTP"

    ```bash
    code-context-agent serve --transport http --host 0.0.0.0 --port 8000
    ```

    Used for networked access by remote MCP clients.

=== "SSE (legacy)"

    ```bash
    code-context-agent serve --transport sse --port 8000
    ```

    Legacy transport for older MCP clients.

## Tools

### `start_analysis`

Kicks off a full codebase analysis. Returns immediately with a `job_id` for polling.

The analysis runs in the background (5--20 minutes) and produces the standard `.code-context/` artifact set (CONTEXT.md, BUNDLE.{area}.md, signatures, heuristic summary).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_path` | `str` | required | Absolute path to the repository root |
| `focus` | `str` | `""` | Optional focus area (e.g., "authentication", "API layer") |
| `issue` | `str` | `""` | Optional GitHub issue reference (e.g., `gh:1694`) |

### `check_analysis`

Polls the status of a running analysis job. Call every 30 seconds until status is `"completed"` or `"error"`.

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | `str` | The job ID returned by `start_analysis` |

Status values: `starting`, `running`, `completed`, `stopped`, `error`.

### `list_repos`

Lists all repositories registered in the code-context-agent multi-repo registry (`~/.code-context/registry.json`). Returns alias, path, analysis timestamp, and artifact count for each repo. Use to discover which codebases are available for querying.

### `git_evolution`

Queries git evolution data that GitNexus does not track: commit-level churn patterns, co-change coupling, bus factor risks, and contributor breakdown.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_path` | `str` | required | Absolute path to repo with `.code-context/` |
| `analysis` | `str` | `"summary"` | One of: `hotspots`, `coupling`, `contributors`, `summary` |

Prerequisite: `.code-context/` must exist from a prior index or analysis run.

### `static_scan_findings`

Reads static analysis findings from the deterministic index (semgrep, type checker, linter, complexity, dead code).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_path` | `str` | required | Absolute path to repo with `.code-context/` |
| `scanner` | `str` | `"all"` | One of: `all`, `semgrep`, `typecheck`, `lint`, `complexity`, `dead_code` |

### `heuristic_summary`

Reads the compact heuristic summary produced by the deterministic indexer. Contains volume, health, git, and GitNexus metrics for the codebase.

| Parameter | Type | Description |
|-----------|------|-------------|
| `repo_path` | `str` | Absolute path to repo with `.code-context/` |

### `review_classification`

Gets the risk-based review classification for a codebase. Routes PRs to the appropriate review level (auto-approve, single review, dual review, or expert review) based on which areas are affected.

| Parameter | Type | Description |
|-----------|------|-------------|
| `repo_path` | `str` | Absolute path to repo with `.code-context/analysis_result.json` |

### `change_verdict`

Computes a change verdict for a PR/diff -- the primary CI/CD integration point. Determines if changes should be auto-merged, require human review, or be blocked. The verdict engine is deterministic (no LLM calls) and runs in under 60 seconds.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_path` | `str` | required | Absolute path to repo with `.code-context/` |
| `base_ref` | `str` | `"main"` | Base git ref for the diff |
| `head_ref` | `str` | `"HEAD"` | Head git ref for the diff |

Exit codes: `0` = auto_merge, `1` = needs_review, `2` = expert, `3` = block.

### `consistency_check`

Checks if code changes are consistent with established architectural patterns. Detects architectural drift by comparing changes against patterns discovered during analysis.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_path` | `str` | required | Absolute path to repo with `.code-context/` |
| `base_ref` | `str` | `"main"` | Base git ref for the diff |
| `head_ref` | `str` | `"HEAD"` | Head git ref for the diff |

### `risk_trend`

Gets temporal risk trends showing how codebase risk is evolving over time. Requires multiple analysis runs to build history.

| Parameter | Type | Description |
|-----------|------|-------------|
| `repo_path` | `str` | Absolute path to repo with `.code-context/history/` |

### `cross_repo_impact`

Checks if code changes affect service contracts (API endpoints, shared schemas, event topics) consumed by other repositories. Requires multiple repos to be indexed in the registry.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_path` | `str` | required | Absolute path to repo |
| `base_ref` | `str` | `"main"` | Base git ref for the diff |
| `head_ref` | `str` | `"HEAD"` | Head git ref for the diff |

## MCP Hints

All MCP tool responses include a `next_steps` field with context-sensitive hints guiding the AI client toward logical follow-up actions. For example:

- After `start_analysis`: suggests polling with `check_analysis` and using GitNexus for immediate queries
- After completed analysis: suggests reading CONTEXT.md, using `git_evolution`, and `static_scan_findings`
- After `change_verdict`: suggests reviewing classification and checking consistency

## Resources

The server provides read-only access to analysis artifacts via URI templates:

| Resource URI | Artifact |
|-------------|----------|
| `analysis://{repo_path}/context` | `CONTEXT.md` -- narrated architecture overview |
| `analysis://{repo_path}/manifest` | `files.all.txt` -- complete file listing |
| `analysis://{repo_path}/signatures` | `CONTEXT.signatures.md` -- compressed signatures |
| `analysis://{repo_path}/bundle` | `CONTEXT.bundle.md` -- curated source bundle |
| `analysis://{repo_path}/result` | `analysis_result.json` -- structured analysis metadata |

## Configuration for Clients

=== "Claude Code"

    Add to your `.mcp.json`:

    ```json
    {
      "mcpServers": {
        "code-context-agent": {
          "command": "code-context-agent",
          "args": ["serve"]
        }
      }
    }
    ```

=== "Cursor"

    Add to your MCP configuration:

    ```json
    {
      "mcpServers": {
        "code-context-agent": {
          "command": "code-context-agent",
          "args": ["serve"],
          "transport": "stdio"
        }
      }
    }
    ```

## Multi-Repo Registry

Completed analyses are automatically registered in `~/.code-context/registry.json`. The `list_repos` tool exposes this registry so MCP clients can discover and switch between analyzed codebases without knowing file paths. See [Multi-Repo Registry](registry.md) for details.

## Typical Workflow

1. Use `list_repos()` to discover available analyzed repositories
2. If not yet analyzed, run `start_analysis(repo_path)` and poll `check_analysis(job_id)` until done
3. Use `heuristic_summary(repo_path)` for a quick metrics overview
4. Use `git_evolution(repo_path, analysis='hotspots')` for churn data
5. Use `static_scan_findings(repo_path)` for security/quality findings
6. Use `change_verdict(repo_path)` in CI/CD to route PRs
7. Read artifacts via resources (e.g., `analysis://repo/path/context`)
