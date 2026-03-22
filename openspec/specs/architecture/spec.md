# Architecture Specification

> Global spec documenting code-context-agent v7.1.0 system architecture.
> Last updated: 2026-03-22

## Purpose

Define the system architecture of code-context-agent: the component layers, execution flow, analysis modes, MCP server design, state management patterns, security boundaries, and dependency map. This spec serves as the authoritative reference for how the system is structured and how components interact.

## System Overview

code-context-agent is a single-agent system that analyzes codebases and produces structured context documentation consumed by AI coding assistants.

| Layer | Component | Source | Purpose |
|-------|-----------|--------|---------|
| CLI | cyclopts App | `cli.py` | Commands: analyze, serve, viz, check |
| Agent | Strands Agent | `agent/factory.py` | Opus 4.6 on Bedrock, 46+ tools, adaptive thinking |
| Runner | AG-UI streaming | `agent/runner.py` | Event stream orchestration, turn/time limits |
| Hooks | HookProviders | `agent/hooks.py` | OutputQuality, ToolEfficiency, FailFast |
| Prompts | Jinja2 templates | `templates/` | system.md.j2 + partials/ + steering/ |
| Tools | @tool functions | `tools/` | Discovery, LSP, Graph, Git, AST, Shell |
| MCP | FastMCP v3 server | `mcp/server.py` | Kickoff/poll, graph query, exploration, resources |
| Models | Pydantic | `models/` | FrozenModel/StrictModel base, AnalysisResult output |
| Config | pydantic-settings | `config.py` | CODE_CONTEXT_ env prefix, cached singleton |
| Display | Rich TUI | `consumer/` | AG-UI event consumer, phase progress, discoveries |

## Execution Flow

```
User CLI invocation
  |
  v
cli.py::analyze()
  |-- validate flags, derive mode (standard|full|focus|incremental)
  |-- fetch issue context (optional, GitHub API)
  |-- build since context (optional, git diff)
  |
  v
agent/runner.py::run_analysis()
  |-- _setup_analysis_context()
  |     |-- create_agent() via factory.py
  |     |     |-- BedrockModel(opus-4.6, adaptive thinking, 1M context)
  |     |     |-- get_analysis_tools() -> 46+ tools + context7 MCP
  |     |     |-- get_prompt(mode) -> Jinja2 rendered system prompt
  |     |     |-- create_all_hooks(full_mode) -> [OutputQuality, ToolEfficiency, ?FailFast]
  |     |     |-- AnalysisResult as structured_output_model
  |     |-- StrandsAgent wrapper (ag-ui-strands)
  |     |-- RichEventConsumer or QuietConsumer
  |
  v
_execute_analysis_stream()
  |-- RunAgentInput -> agui_agent.run()
  |-- async for event in stream:
  |     |-- dispatch to consumer via _EVENT_HANDLERS
  |     |-- count turns on TEXT_MESSAGE_END
  |     |-- enforce max_turns and max_duration
  |-- cleanup: consumer.stop(), LSP session shutdown (10s timeout)
  |
  v
Return dict: {status, output_dir, context_path, turn_count, duration_seconds}
```

## Analysis Modes

| Mode | CLI Flags | Max Duration | Max Turns | Behavior |
|------|-----------|-------------|-----------|----------|
| standard | (none) | 1200s (20m) | 1000 | Default balanced analysis |
| full | `--full` | 3600s (60m) | 3000 | Exhaustive, FailFastHook, all files read |
| focus | `--focus "area"` | 1200s | 1000 | Prioritize focus area in all phases |
| incremental | `--since ref` | 1200s | 1000 | Skip phase 1, only re-analyze changed files |
| full+focus | `--full --focus` | 3600s | 3000 | Full mode with focus prioritization |

## MCP Server Architecture

The FastMCP v3 server exposes three tool types and six resource templates:

**Tools (kickoff/poll pattern):**
- `start_analysis(repo_path, focus?, issue?)` -- spawns background asyncio task, returns job_id
- `check_analysis(job_id)` -- polls job status from module-level `_jobs` dict
- `query_code_graph(repo_path, algorithm, ...)` -- 10 graph algorithms on persisted graph
- `explore_code_graph(repo_path, action, ...)` -- progressive disclosure exploration
- `get_graph_stats(repo_path)` -- quick graph summary

**Resources:**
- `analysis://{repo_path}/context` -- CONTEXT.md
- `analysis://{repo_path}/graph` -- code_graph.json
- `analysis://{repo_path}/manifest` -- files.all.txt
- `analysis://{repo_path}/signatures` -- CONTEXT.signatures.md
- `analysis://{repo_path}/bundle` -- CONTEXT.bundle.md
- `analysis://{repo_path}/result` -- analysis_result.json

**Transport:** stdio (default for Claude Desktop), http (Streamable HTTP), sse (legacy)

## State Management

| State | Location | Lifecycle | Pattern |
|-------|----------|-----------|---------|
| Settings | `config.py` | Process lifetime | `@lru_cache` singleton via `get_settings()` |
| Code graphs | `tools/graph/tools.py` | Analysis session | Module-level `_graphs: dict[str, CodeGraph]` |
| Explorers | `tools/graph/tools.py` | Analysis session | Module-level `_explorers: dict[str, ProgressiveExplorer]` |
| LSP sessions | `tools/lsp/session.py` | Analysis session | Singleton `LspSessionManager` with fallback chains |
| MCP jobs | `mcp/server.py` | Server lifetime | Module-level `_jobs: dict[str, dict]` |
| Phase tracking | `consumer/state.py` | Analysis session | `AnalysisState` in consumer |

## Security Boundaries

| Boundary | Mechanism | Source |
|----------|-----------|--------|
| Shell commands | Allowlist of read-only programs (ALLOWED_PROGRAMS frozenset) | `tools/shell_tool.py` |
| Git operations | Read-only subcommand whitelist (GIT_READ_ONLY frozenset) | `tools/shell_tool.py` |
| Shell operators | Regex blocking of `;`, `&`, `|`, backticks, `$()`, redirects | `tools/shell_tool.py` |
| Path traversal | Sensitive directory blocking (/etc, /root, /boot, /proc, /sys) | `tools/shell_tool.py` |
| File writes | Restricted to `.code-context/` directories only | `tools/discovery.py::write_file` |
| Input validation | `validate_repo_path`, `validate_file_path`, `validate_search_pattern` | `tools/validation.py` |
| Output truncation | MAX_OUTPUT_SIZE = 100,000 chars per tool result | `agent/hooks.py`, `tools/shell_tool.py` |

## Dependencies (runtime)

| Package | Role |
|---------|------|
| strands-agents | Agent framework, @tool decorator, hooks |
| strands-agents-tools | graph (multi-agent DAG) tool |
| ag-ui-protocol | AG-UI event types |
| ag-ui-strands | StrandsAgent wrapper for event streaming |
| networkx[default,extra] | Code graph model and algorithms |
| fastmcp | MCP v3 server |
| cyclopts | CLI framework |
| pydantic + pydantic-settings | Models and configuration |
| jinja2 | System prompt templates |
| rich | TUI display |
| loguru | Structured logging |
| ty | Python type checker (also used as LSP server) |

## External CLI Dependencies

| Tool | Purpose | Required |
|------|---------|----------|
| rg (ripgrep) | File search, manifest creation | Yes |
| ast-grep | Pattern matching, rule packs | Yes |
| repomix | Code bundling, signatures, orientation | Yes |
| npx | context7 MCP server launcher | Optional |
| jscpd | Clone detection | Optional |

## Requirements

### Requirement: The system SHALL create exactly one Strands Agent per analysis run
Agent is stateless between runs. All per-run state MUST live in module-level dicts keyed by graph name.

#### Scenario: Standard analysis run
- **WHEN** `run_analysis()` is called with mode="standard"
- **THEN** one Agent is created with 46+ tools, max_turns=1000, max_duration=1200s

#### Scenario: Full mode analysis run
- **WHEN** `run_analysis()` is called with mode="full"
- **THEN** one Agent is created with FailFastHook, max_turns=3000, max_duration=3600s

### Requirement: The MCP server SHALL use kickoff/poll pattern for long-running analysis
Analysis runs 5-20 minutes; MCP clients timeout faster. Background asyncio task MUST be tracked in module-level _jobs dict.

#### Scenario: Client starts analysis
- **WHEN** `start_analysis(repo_path)` is called
- **THEN** returns immediately with job_id, spawns background task

#### Scenario: Client polls for completion
- **WHEN** `check_analysis(job_id)` is called and analysis is complete
- **THEN** returns status="completed" with artifact availability map

### Requirement: All tool functions SHALL return JSON strings
Success format MUST be `{"status": "success", ...payload}`. Error format MUST be `{"status": "error", "error": "message"}`.

#### Scenario: Tool succeeds
- **WHEN** any @tool function completes successfully
- **THEN** it returns a JSON string with `"status": "success"` and relevant data

#### Scenario: Tool fails
- **WHEN** any @tool function encounters an error
- **THEN** it returns a JSON string with `"status": "error"` and `"error"` message

### Requirement: LSP sessions SHALL use ordered fallback chains
Primary server failure MUST trigger the next server in the chain. Per-language chains MUST be defined in Settings.lsp_servers.

#### Scenario: Primary LSP server returns empty results
- **WHEN** lsp_document_symbols returns no results from "ty server"
- **THEN** `_try_fallback_session()` attempts "pyright-langserver --stdio"

### Requirement: The event stream SHALL enforce turn and duration limits
The runner MUST count TEXT_MESSAGE_END events as turns and MUST check elapsed wall-clock time on every event.

#### Scenario: Agent exceeds max turns
- **WHEN** turn count exceeds max_turns during streaming
- **THEN** streaming stops, status="stopped", exceeded_limit records the limit hit

#### Scenario: Agent exceeds max duration
- **WHEN** elapsed time exceeds max_duration during streaming
- **THEN** streaming stops, status="stopped", exceeded_limit records the limit hit

### Requirement: Security boundaries SHALL prevent unauthorized operations
The shell tool MUST validate all commands against an allowlist before execution. File writes MUST be restricted to .code-context/ directories.

#### Scenario: Non-allowlisted program
- **WHEN** `shell("curl http://example.com")` is called
- **THEN** command is blocked with "not in the allowed programs list"

#### Scenario: Shell operator injection
- **WHEN** `shell("ls; rm -rf /")` is called
- **THEN** command is blocked with "shell operator not allowed"

#### Scenario: Write outside output directory
- **WHEN** `write_file("/etc/passwd", "content")` is called
- **THEN** write is denied with "not within a .code-context/ directory"
