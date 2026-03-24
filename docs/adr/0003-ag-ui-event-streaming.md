# ADR-0003: AG-UI Event Streaming Protocol

**Date**: 2025-03-01

**Status**: Superseded — AG-UI dependencies removed in v8; the agent now uses native Strands callback hooks for event streaming.

## Context

The analysis agent runs for 5-20 minutes producing 40+ tool calls per session. Users need real-time visibility into agent progress for the Rich TUI display, including:

- Text message streaming (assistant thinking/writing)
- Tool call start/args/result/end lifecycle
- Run-level events (started, finished, error)
- State snapshots for progress tracking

Alternatives considered:

- **Custom SSE/WebSocket**: Full control but requires defining event types, serialization, and consumer protocol from scratch
- **Strands callback_handler directly**: Simpler but untyped; no standardized event schema for external consumers
- **No streaming (batch output)**: Simplest but unacceptable UX for 20-minute analysis runs

## Decision

Use the AG-UI protocol (`ag-ui-protocol` + `ag-ui-strands`) for typed event streaming between the agent and display consumers.

The implementation in `src/code_context_agent/agent/runner.py`:

1. The Strands agent is wrapped in `StrandsAgent` from `ag-ui-strands`, which translates Strands callbacks into typed AG-UI events
2. `RunAgentInput` provides the standard AG-UI input format with `thread_id`, `run_id`, `messages`, and `state`
3. Events are consumed via `async for event in agui_agent.run(input_data)` and dispatched to an `EventConsumer` interface
4. A dispatch registry (`_EVENT_HANDLERS`) maps `EventType` enums to handler functions for clean event routing
5. `RichEventConsumer` renders events as a Rich TUI with live panels for text, tool calls, and progress
6. `QuietConsumer` silently accumulates events for programmatic use (MCP server, tests)

Turn counting and duration limits are enforced at the event stream level: `TEXT_MESSAGE_END` events increment the turn counter, and both `max_turns` and `max_duration` trigger graceful stream termination.

## Consequences

**Positive:**

- Standardized event types (`EventType.TEXT_MESSAGE_START`, `TOOL_CALL_START`, `RUN_FINISHED`, etc.) provide a clean contract between agent execution and display
- The `EventConsumer` interface decouples display from execution; swapping Rich TUI for a web UI or log sink requires only a new consumer implementation
- AG-UI's typed events enable the MCP server's kickoff/poll pattern to report granular progress

**Negative:**

- Requires monkey-patching `StrandsAgent.__init__` to preserve the `callback_handler` from the original agent (lines 33-43 of `runner.py`); without this patch, `StrandsAgent` creates per-thread agents that default to `PrintingCallbackHandler`, causing duplicate console output
- Adds two dependencies (`ag-ui-protocol>=0.1.13`, `ag-ui-strands>=0.1.1`) that are relatively early-stage libraries
- The `StrandsAgent` wrapper does not expose all Strands agent configuration (e.g., `hooks` must be set on the inner agent before wrapping)

**Neutral:**

- Event types align with the emerging AG-UI standard, positioning for future interop with AG-UI compatible frontends
- The dispatch pattern in `_EVENT_HANDLERS` mirrors the shell tool's command validation pattern, maintaining codebase consistency
