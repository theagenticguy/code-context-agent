# ADR-0012: Strands Swarm Multi-Agent Pipeline

**Date**: 2025-06-15

**Status**: accepted (supersedes single-agent analysis from [ADR-0001](0001-strands-agents-framework.md))

## Context

- v7 used a single Strands Agent with 50+ tools and a monolithic system prompt
- Analysis quality suffered from context window saturation — by the time the agent reached synthesis, earlier tool results were compressed or lost
- The agent struggled to balance breadth (graph algorithms, git history) with depth (file reading, code understanding)
- AG-UI event streaming ([ADR-0003](0003-ag-ui-event-streaming.md)) added complexity for TUI display without providing multi-agent capabilities

## Decision

Replace the single-agent analysis with a 4-node Strands Swarm pipeline: `structure_analyst -> history_analyst -> code_reader -> synthesizer`.

- Each node gets a focused tool set and system prompt (specialist pattern)
- Pre-built index graph is loaded into `_graphs["main"]` before Swarm starts, so agents query the graph immediately
- AG-UI dependency removed; display driven by HookProviders (`SwarmDisplayHook`, `ToolDisplayHook`) that update `AgentDisplayState`
- `create_all_hooks()` in `src/code_context_agent/agent/hooks.py` returns `(agent_hooks, swarm_hooks)` tuple — agent hooks registered on each node, swarm hooks on the Swarm itself
- Nodes execute sequentially (safe for shared module-level state like `_graphs`)
- Only the final node (synthesizer) has `structured_output_model=AnalysisResult`
- All nodes use `callback_handler=None` to prevent duplicate event dispatch
- Swarm is created in `src/code_context_agent/agent/swarm.py` via `create_analysis_swarm()`
- Analysis execution in `src/code_context_agent/agent/runner.py` uses `swarm.invoke_async()` with hook-based display

## Consequences

**Positive:**

- Each specialist agent operates within a focused context window, reducing saturation
- Tool assignments per node prevent misuse (e.g., `history_analyst` cannot call LSP tools)
- Graph preloading eliminates redundant index-building across agents
- Hook-driven display is simpler than AG-UI event streaming (no monkey-patching, no protocol dependency)
- Sequential execution with handoff context maintains coherence across analysis phases

**Negative:**

- Total token usage increases (4 separate context windows vs 1)
- Handoff context is text-only (`SharedContext`) — no structured data transfer between nodes
- `create_agent()` in `src/code_context_agent/agent/factory.py` is now legacy (only used by indexer), adding maintenance surface

**Neutral:**

- Swarm `max_handoffs=10` and `max_iterations=10` provide safety bounds against infinite loops
- Node-level `node_timeout=300s` prevents individual agents from running indefinitely
- The old agents-as-tools pattern in `src/code_context_agent/agent/analysts.py` is retained as fallback reference but not used in the main pipeline
