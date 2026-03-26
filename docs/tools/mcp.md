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
| `flows` | Trace execution flows through the graph | -- |
| `blast_radius` | BFS blast radius from a node | `node_a` |

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

### `list_repos`

Lists all repositories registered in the code-context-agent multi-repo registry (`~/.code-context/registry.json`). Returns alias, path, analysis timestamp, graph existence, and artifact count for each repo. Use to discover which codebases are available for querying.

### `diff_impact`

Maps a git diff (changed files and line numbers) to impacted graph nodes and suggests tests to run. Combines line-to-node mapping, per-node blast radius, result merging, and test suggestion via TESTS edges. Accepts a JSON array of changed files with line numbers.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_path` | `str` | required | Absolute path to repo with code graph |
| `changed_files` | `str` | required | JSON array: `[{"file_path": "src/foo.py", "lines": [10, 11, 12]}]` |
| `max_depth` | `int` | `3` | Max BFS depth for blast radius per symbol |
| `top_k` | `int` | `20` | Max affected nodes to return |

### `execute_cypher`

Executes a read-only Cypher query against a KuzuDB-backed code graph. Only available when the graph was built with the KuzuDB backend (`CODE_CONTEXT_GRAPH_BACKEND=kuzu`). Write operations (CREATE, DELETE, SET, MERGE, DROP, ALTER) are blocked.

| Parameter | Type | Description |
|-----------|------|-------------|
| `repo_path` | `str` | Absolute path to repo with KuzuDB graph |
| `query` | `str` | Read-only Cypher query |

## MCP Hints

All MCP tool responses include a `next_steps` field with context-sensitive hints guiding the AI client toward logical follow-up actions. For example:

- After `hotspots` query: suggests expanding top hotspot and checking coupling
- After `overview` exploration: suggests expanding the top hotspot node or largest module
- After `diff_impact`: suggests reviewing suggested tests and checking aggregate risk

Hints are defined per-algorithm and per-action in `QUERY_ALGORITHM_HINTS` and `EXPLORE_ACTION_HINTS` maps. This helps AI clients navigate the graph without prior knowledge of the tool surface.

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

## Multi-Repo Registry

Completed analyses are automatically registered in `~/.code-context/registry.json`. The `list_repos` tool exposes this registry so MCP clients can discover and switch between analyzed codebases without knowing file paths. Graphs are cached in memory with a 5-minute TTL for fast repeated queries.

## Typical Workflow

1. Use `list_repos()` to discover available analyzed repositories
2. Check if `.code-context/code_graph.json` exists in the target repository
3. If not, run `start_analysis(repo_path)` and poll `check_analysis(job_id)` until done
4. Use `explore_code_graph(action="overview")` for a high-level view
5. Use `query_code_graph(algorithm="hotspots")` to find critical code
6. Drill down with `explore_code_graph(action="expand_node", node_id="...")` on interesting results
7. Use `diff_impact(changed_files=...)` to assess PR impact and get test suggestions
8. Read artifacts via resources for full content (e.g., `analysis://repo/path/context`)
