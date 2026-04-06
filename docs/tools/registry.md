# Multi-Repo Registry

The registry tracks all analyzed repositories in a central location (`~/.code-context/registry.json`), enabling MCP clients to discover and switch between codebases.

## How It Works

When an analysis completes (via `start_analysis` MCP tool or the `analyze` CLI command), the repository is automatically registered using the repository directory name as the alias. The registry stores:

| Field | Description |
|-------|-------------|
| `alias` | Short name derived from the repo directory name |
| `path` | Resolved absolute path to the repository |
| `analyzed_at` | ISO 8601 timestamp of the analysis |
| `graph_exists` | Whether analysis artifacts were produced |
| `artifact_count` | Number of files in `.code-context/` |

## MCP Integration

### `list_repos`

The MCP server exposes `list_repos()` to discover available repositories:

```json
{
    "repos": [
        {
            "alias": "my-app",
            "path": "/Users/me/projects/my-app",
            "analyzed_at": "2026-03-22T10:30:00+00:00",
            "graph_exists": true,
            "artifact_count": 9
        }
    ],
    "count": 1
}
```

AI clients call `list_repos` first to discover what is available, then pass the `path` value to `git_evolution`, `static_scan_findings`, `heuristic_summary`, or other MCP tools.

## Graph Caching

Graphs loaded from registered repos are cached in memory with a 5-minute TTL. Repeated queries to the same repo within that window skip disk I/O.

## Registry Location

The registry file lives at `~/.code-context/registry.json`. It is created automatically on first analysis. The file is written atomically (write to temp file, then rename) to prevent corruption from concurrent writes.

## Programmatic API

The `Registry` class in `code_context_agent.mcp.registry` provides:

| Method | Description |
|--------|-------------|
| `register(alias, repo_path)` | Register or update a repo entry |
| `unregister(alias)` | Remove a repo from the registry |
| `list_repos()` | List all registered repos |
| `get_repo(alias)` | Get a single repo entry by alias |
| `find_by_path(repo_path)` | Find alias by resolved repo path |
| `load_graph(alias)` | Load graph with 5-min TTL caching |
