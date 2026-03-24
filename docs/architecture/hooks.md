# Hook System

code-context-agent uses Strands HookProviders to guide agent behavior without
modifying tool implementations. Hooks intercept events (tool calls, model
invocations, Swarm node transitions) and can log, warn, enrich, or halt execution.

All 9 hook providers live in `src/code_context_agent/agent/hooks.py`.
See [Swarm Pipeline](swarm.md) for how hooks integrate with the multi-agent pipeline.

---

## Hook overview

| Hook | Level | Event | Purpose |
|------|-------|-------|---------|
| `ConversationCompactionHook` | Agent | `BeforeInvocationEvent` | Strips large tool payloads from older messages to prevent context window overflow |
| `OutputQualityHook` | Agent | `AfterToolCallEvent` | Warns when tool outputs exceed 100K chars |
| `ToolEfficiencyHook` | Agent | `BeforeToolCallEvent` | Warns when `shell` is used for tasks that have dedicated tools |
| `ReasoningCheckpointHook` | Agent | `AfterToolCallEvent` | Injects reasoning prompts after key analysis tools to force LLM interpretation |
| `FailFastHook` | Agent | `AfterToolCallEvent` | Raises `FullModeToolError` when non-exempt tools return errors in `--full` mode |
| `ToolDisplayHook` | Agent | `Before/AfterToolCallEvent` | Updates `AgentDisplayState` with active tool info for Rich TUI |
| `JsonLogHook` | Agent | `Before/AfterToolCallEvent` | Emits structured JSON log lines for `--quiet` mode |
| `SwarmDisplayHook` | Swarm | `Before/AfterNodeCallEvent` | Tracks Swarm node transitions for multi-agent TUI display |
| `JsonLogSwarmHook` | Swarm | `Before/AfterNodeCallEvent` | Emits JSON log lines for Swarm agent transitions |

---

## Hook creation

`create_all_hooks()` is the single entry point for assembling all hooks:

```python
agent_hooks, swarm_hooks = create_all_hooks(
    full_mode=True,      # Include FailFastHook
    state=display_state,  # AgentDisplayState for TUI (None if quiet)
    quiet=False,          # Use JsonLogHook instead of display hooks
)
```

- **Agent hooks** are registered on each Swarm node agent. They handle tool-level
  events (`BeforeToolCallEvent`, `AfterToolCallEvent`, `BeforeInvocationEvent`).
- **Swarm hooks** are registered on the Swarm itself. They handle node-level
  events (`BeforeNodeCallEvent`, `AfterNodeCallEvent`).

The split ensures agent-level events (tool calls) and swarm-level events (node
transitions) are handled by the right providers. The four core agent hooks
(`ConversationCompactionHook`, `OutputQualityHook`, `ToolEfficiencyHook`,
`ReasoningCheckpointHook`) are always active. Display and fail-fast hooks are
conditional on CLI flags.

---

## Detailed hook descriptions

### ConversationCompactionHook

Fires before every model invocation via `BeforeInvocationEvent`. Walks the
conversation history, skips the last 4 messages (current turn), and replaces
tool payloads exceeding 2000 chars with stubs:

```
[Tool output consumed (15432 chars) -- see reasoning above]
```

Both `toolResult` content and large `toolUse` input blocks are compacted. The
model's reasoning about tool results is preserved -- only raw data is replaced.

!!! note "Why this matters"
    A typical analysis produces 50+ tool calls. Without compaction, accumulated
    tool results can exhaust the 1M context window before the synthesizer runs.

### OutputQualityHook

Fires after every tool call. Logs a warning via loguru when the result string
exceeds 100,000 characters. This is a diagnostic signal -- it does not block
execution, but flags tools that may need pagination or filtering.

### ToolEfficiencyHook

Fires before every tool call. When the agent calls `shell`, inspects the command
for patterns that have dedicated tools:

| Shell pattern | Recommended tool |
|---------------|------------------|
| `grep` / `rg ` | `rg_search` |
| `cat ` | `read_file_bounded` |
| `tree ` | `create_file_manifest` (never on repo root) |
| `find ` | `create_file_manifest` or `rg_search` |

The warning is logged but does not block the call. The prompt's steering
directives reinforce these preferences so the LLM self-corrects over time.

### ReasoningCheckpointHook

Fires after key analysis tools complete successfully. Appends a reasoning prompt
to the tool result content, forcing the LLM to interpret data before collecting
more.

**Monitored tools and prompts:**

- **`code_graph_analyze`** -- "What structural pattern do they reveal? Which files
  appear as bottlenecks or foundations?"
- **`code_graph_explore`** -- "Are there unexpected clusters, isolated components,
  or surprising dependency directions?"
- **`git_hotspots`** -- "Which high-churn files overlap with structurally central
  files? High churn + high centrality = fragile bottleneck."
- **`git_files_changed_together`** -- "Do these co-change patterns match the
  static dependency graph? Files that change together WITHOUT a static dependency
  edge indicate implicit coupling."
- **`git_blame_summary`** -- "Single-author files with high centrality = bus
  factor risk. Many-author files with complex logic = coordination risk."
- **`read_file_bounded`** -- "Compare what you see against what the graph metrics
  predicted. What domain invariants does this file maintain?"

Prompts are skipped if the tool returned an error.

### FailFastHook

Only active in `--full` mode. Fires after every tool call, parses the result as
JSON, and raises `FullModeToolError` if `status` is `"error"` and the tool is
not exempt.

**Exempt tools:**

- `rg_search`, `lsp_workspace_symbols` -- search tools may legitimately return no results
- `lsp_shutdown` -- shutdown is best-effort
- `code_graph_load` -- may fail if no prior graph exists
- `context7_resolve-library-id`, `context7_query-docs` -- external MCP tools may be unavailable
- `shell` -- user-controlled

See [Full Mode](../getting-started/full-mode.md) for the broader `--full` pipeline.

### Display hooks (SwarmDisplayHook, ToolDisplayHook)

These hooks update `AgentDisplayState`, which the Rich `Live` renderer polls at
2 fps. They replaced AG-UI event streaming in v8.

- **`SwarmDisplayHook`** tracks which specialist agent is currently active by
  responding to `BeforeNodeCallEvent` / `AfterNodeCallEvent`. It calls
  `state.set_active_agent()` and `state.complete_agent()`.
- **`ToolDisplayHook`** tracks active tool calls, completed tools, and error
  counts by responding to `BeforeToolCallEvent` / `AfterToolCallEvent`. It
  creates `ToolCallState` entries and appends them to `state.completed_tools`.

See [TUI & Phases](tui-phases.md) for the full display architecture.

### JSON log hooks (JsonLogHook, JsonLogSwarmHook)

Used in `--quiet` mode (CI/CD pipelines). Output structured JSON lines via
loguru with `logger.bind(output="json")`.

- **`JsonLogHook`** emits `tool_start` and `tool_end` events with tool name and
  status (`ok` or `error`).
- **`JsonLogSwarmHook`** emits `agent_start` and `agent_end` events with the
  Swarm node ID.

---

## Adding a new hook

1. Create a class inheriting from `HookProvider` in `agent/hooks.py`.
2. Implement `register_hooks(self, registry: HookRegistry, **kwargs)` to register
   callbacks for typed events.
3. Callbacks receive typed events (`BeforeToolCallEvent`, `AfterToolCallEvent`,
   `BeforeInvocationEvent`, `BeforeNodeCallEvent`, `AfterNodeCallEvent`).
4. Add the hook to `create_all_hooks()` in the appropriate list -- `agent_hooks`
   for tool/invocation events, `swarm_hooks` for node transition events.

```python
class MyCustomHook(HookProvider):
    """One-line description of what this hook does."""

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self._on_tool_end)

    def _on_tool_end(self, event: AfterToolCallEvent, **kwargs: Any) -> None:
        tool_name = event.tool_use.get("name", "")
        # ... custom logic ...
```

!!! tip
    Keep hooks stateless when possible. If state is needed (e.g., display hooks),
    accept it via `__init__` and store as `self._state`.
