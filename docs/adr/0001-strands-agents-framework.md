# ADR-0001: Use Strands Agents as the Agent Framework

**Date**: 2025-01-15

**Status**: accepted

## Context

code-context-agent requires an agent framework that supports:

- Bedrock-native model invocation (Claude Opus 4.6 via `global.anthropic.claude-opus-4-6-v1`)
- Tool-calling with 40+ tools across discovery, LSP, graph, git, AST, and shell categories
- Structured output via Pydantic models (the agent produces an `AnalysisResult`)
- Extensible hook system for output quality enforcement and tool efficiency guidance
- Multi-agent orchestration for parallel sub-tasks

Alternatives considered:

- **LangChain/LangGraph**: Mature ecosystem but heavy abstraction layers, non-trivial Bedrock integration, opinionated about state management
- **Custom agent loop**: Full control but significant engineering investment for tool dispatch, retry logic, and streaming
- **AutoGen**: Multi-agent focused but less mature Bedrock support at the time

## Decision

Use `strands-agents` (with `strands-agents-tools` for the `graph` orchestration tool) as the agent framework.

The agent is created in `src/code_context_agent/agent/factory.py` via `create_agent()`, which configures:

- `BedrockModel` with adaptive thinking and 1M context window (`anthropic_beta: context-1m-2025-08-07`)
- `structured_output_model=AnalysisResult` for Pydantic-validated output
- `HookProvider` instances (`OutputQualityHook`, `ToolEfficiencyHook`, `FailFastHook`) registered via `HookRegistry`
- Tools loaded inside `get_analysis_tools()` with function-level imports to avoid circular dependencies
- `MCPClient` integration for context7 library documentation lookup

All tools use the `@tool` decorator from `strands` and return JSON strings. The `strands_tools.graph` tool enables multi-agent DAG orchestration for parallel analysis phases.

## Consequences

**Positive:**

- Native Bedrock integration with zero adapter code; `BedrockModel` handles authentication, region routing, and model-specific parameters
- `HookProvider` system enables non-invasive agent guidance (e.g., `ToolEfficiencyHook` warns when `shell` is used instead of `rg_search`)
- `MCPClient` is a first-class `ToolProvider`, making MCP server integration seamless (context7 attaches with 3 lines of code)
- `structured_output_model` enforces schema compliance on agent output without post-processing

**Negative:**

- Coupled to the AWS/Bedrock ecosystem; switching to OpenAI or Anthropic direct API would require replacing `BedrockModel`
- Monkey-patching required for `StrandsAgent.__init__` to preserve `callback_handler` (see `runner.py` lines 33-43)
- Fewer community examples and plugins compared to LangChain

**Neutral:**

- Tool functions follow a strict pattern: `@tool` decorator, docstring-as-description, JSON string return value
- The `graph` tool from `strands_tools` is the only external tool; all others are custom
