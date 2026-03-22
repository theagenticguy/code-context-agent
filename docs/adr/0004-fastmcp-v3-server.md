# ADR-0004: FastMCP v3 for MCP Server

**Date**: 2025-04-01

**Status**: accepted

## Context

AI coding assistants (Claude Code, Cursor, Windsurf) can consume MCP servers to gain new capabilities. code-context-agent produces valuable analysis artifacts (code graphs, narrated context, business logic rankings) that assistants should be able to access programmatically.

Key requirements:

- Expose long-running analysis as a non-blocking operation (analysis takes 5-20 minutes, exceeding MCP client timeouts)
- Expose graph algorithms as fast, interactive tools
- Provide read-only access to analysis artifacts via MCP resources
- Support stdio, HTTP, and SSE transports for different client environments

Alternatives considered:

- **Raw MCP SDK (`mcp` package)**: Lower level, requires manual JSON-RPC handling, no resource decorator pattern
- **Expose all 40+ agent tools as MCP tools**: Would duplicate commodity tools (ripgrep, LSP, git) already available in the MCP ecosystem

## Decision

Use FastMCP v3 (`fastmcp>=3.0.2,<4`) with a deliberate tool selection strategy: expose only differentiator tools that AI assistants cannot get elsewhere.

The server is implemented in `src/code_context_agent/mcp/server.py` and exposes:

**Tools (4):**
- `start_analysis` / `check_analysis`: Kickoff/poll pattern for long-running analysis. Jobs are tracked in a module-level `_jobs` dict with `asyncio.create_task` for background execution.
- `query_code_graph`: Dispatch-based router to 10 graph algorithms (hotspots, foundations, trust, modules, entry_points, coupling, similar, dependencies, category, triangles)
- `explore_code_graph`: Progressive disclosure with 6 actions (overview, expand_node, expand_module, path, category, status)

**Resources (6):**
- `analysis://{repo_path}/context` through `analysis://{repo_path}/result` for reading CONTEXT.md, code_graph.json, files.all.txt, signatures, bundle, and analysis_result.json

Commodity tools (ripgrep search, LSP symbols, git history, AST-grep patterns, shell) are intentionally excluded. The server's `instructions` field documents when to use each tool and the recommended workflow.

## Consequences

**Positive:**

- `@mcp.tool` and `@mcp.resource` decorators provide clean, type-annotated tool definitions with `Annotated[str, Field(description=...)]` parameter descriptions
- FastMCP handles JSON serialization (tools return dicts, not JSON strings), transport negotiation (stdio/HTTP/SSE), and MCP protocol compliance
- The kickoff/poll pattern avoids MCP client timeouts; `check_analysis` returns immediately with job status and artifact availability
- Docstrings with `USE THIS WHEN` / `DO NOT USE IF` patterns help AI assistants select the right tool

**Negative:**

- Only 4 tools exposed means assistants must use other MCP servers (or built-in tools) for commodity operations like file search and git history
- Module-level `_jobs` dict means job state is lost on server restart; no persistence layer
- The `_load_graph()` helper reads and deserializes the full JSON graph on every tool call (no caching at the MCP layer)

**Neutral:**

- The server is started via `code-context-agent serve` CLI command, which delegates to `mcp.run()`
- Graph algorithms are dispatched via `_build_algorithm_dispatch()` and `_build_explore_dispatch()` helper functions that return callable dispatch tables
