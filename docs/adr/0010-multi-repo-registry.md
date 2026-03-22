# ADR-0010: Multi-Repo Registry

**Date**: 2026-03-22

**Status**: accepted

## Context

The MCP server (`code-context-agent serve`) could only serve one repository at a time. The repo path was either passed as an argument or inferred from the working directory. This forced users to run separate MCP server instances for each repo, which is impractical when AI coding assistants work across multiple repositories simultaneously (e.g., a service and its shared library, or a frontend and backend pair).

Alternatives considered:

- **Multiple MCP server instances**: One per repo, each on a different port. Works but requires manual coordination, wastes resources, and MCP client configuration becomes complex.
- **SQLite registry**: Durable and queryable, but heavy for what is essentially a small key-value store of repo metadata.
- **In-memory registry**: Simple but lost on restart, defeating the purpose of persistent cross-session access.

## Decision

Implement a JSON file registry at `~/.code-context/registry.json` that tracks analyzed repositories with alias-based addressing.

Key design choices:

- **JSON file storage** at a well-known path (`~/.code-context/registry.json`) — human-readable, easy to debug, no dependencies
- **Atomic writes** via tempfile + rename to prevent corruption if the process is interrupted mid-write
- **Alias-based addressing**: Each repo gets a short alias (derived from its directory name) for use in MCP tool calls instead of full paths
- **Lazy graph loading** with a 5-minute TTL cache — graphs are loaded from disk only when a tool references that repo, and cached to avoid repeated disk reads
- **Auto-registration**: Running `code-context-agent analyze /path/to/repo` automatically registers the repo in the registry after successful analysis

## Consequences

**Positive:**

- A single MCP server instance serves all previously analyzed repos
- `list_repos` tool enables AI assistants to discover available repos without prior knowledge of paths
- Alias-based addressing is concise and stable (e.g., `repo: "backend"` instead of `repo_path: "/home/user/projects/my-backend-service"`)
- Atomic writes prevent registry corruption
- Backward compatible — `repo_path` parameter still works for direct access without registration

**Negative:**

- Registry is a single JSON file; concurrent writes from multiple processes could conflict (mitigated by atomic writes but not fully locked)
- Aliases derived from directory names can collide if two repos have the same directory name; manual alias override is required in that case
- 5-minute TTL cache means a repo re-analyzed in another terminal won't reflect updates for up to 5 minutes in the MCP server

**Neutral:**

- Registry file is small (metadata only, no graph data) and grows linearly with the number of analyzed repos
- Manual registry management (add/remove/rename aliases) is possible by editing the JSON file directly
