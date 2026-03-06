# MCP Server

The MCP server exposes code-context-agent's core differentiators via the [Model Context Protocol](https://modelcontextprotocol.io), enabling coding agents (Claude Code, Cursor, etc.) to use analysis capabilities directly.

Commodity tools (ripgrep search, LSP symbols, git history, ast-grep) are intentionally not exposed -- they are already available in the MCP marketplace. The server focuses on capabilities that are unique to code-context-agent.

## Starting the Server

=== "stdio (default)"

    ```bash
    code-context-agent serve
    ```

    Used for local MCP clients like Claude Code and Claude Desktop.

=== "HTTP"

    ```bash
    code-context-agent serve --transport http --port 8000
    ```

    Used for networked access by remote MCP clients.

## Tools

### `start_analysis`

Kicks off a full codebase analysis. Returns immediately with a `job_id` for polling.

The analysis runs in the background (5--20 minutes) and produces the standard `.code-context/` artifact set.

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

### `query_code_graph`

Runs graph algorithms on a pre-built code graph. Requires `.code-context/code_graph.json` from a prior analysis.

| Algorithm | Description | Requires |
|-----------|-------------|----------|
| `hotspots` | Betweenness centrality -- bottleneck/integration code | -- |
| `foundations` | PageRank -- core infrastructure | -- |
| `trust` | TrustRank -- noise-resistant importance scoring | -- |
| `modules` | Louvain community detection -- logical clusters | -- |
| `entry_points` | Nodes with no incoming edges | -- |
| `coupling` | Connection strength between two nodes | `node_a`, `node_b` |
| `similar` | Personalized PageRank from a node | `node_a` |
| `dependencies` | BFS traversal of transitive dependencies | `node_a` |
| `triangles` | Tightly-coupled triads | -- |
| `category` | Nodes in a business logic category | `category` |

### `explore_code_graph`

Progressive graph exploration, starting broad and drilling down.

| Action | Description | Requires |
|--------|-------------|----------|
| `overview` | Entry points, hotspots, modules, foundations | -- |
| `expand_node` | Neighbors and relationships of a node | `node_id` |
| `expand_module` | Internals of a detected module | `module_id` |
| `path` | Shortest path between two nodes | `node_id`, `target_node` |
| `category` | All nodes in a business logic category | `category` |
| `status` | Current exploration state | -- |

### `get_graph_stats`

Returns summary statistics (node/edge counts by type, density) for a repository's code graph.

## Resources

The server provides read-only access to analysis artifacts via URI templates:

| Resource URI | Artifact |
|-------------|----------|
| `analysis://{repo_path}/context` | `CONTEXT.md` -- narrated architecture overview |
| `analysis://{repo_path}/graph` | `code_graph.json` -- structural graph data |
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

## Typical Workflow

1. Check if `.code-context/code_graph.json` exists in the target repository
2. If not, run `start_analysis(repo_path)` and poll `check_analysis(job_id)` until done
3. Use `explore_code_graph(action="overview")` for a high-level view
4. Use `query_code_graph(algorithm="hotspots")` to find critical code
5. Drill down with `explore_code_graph(action="expand_node", node_id="...")` on interesting results
6. Read artifacts via resources for full content (e.g., `analysis://repo/path/context`)
