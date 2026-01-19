# PR: Preserve callback_handler when creating per-thread agents

## Summary

The `StrandsAgent` wrapper creates per-thread agent instances but doesn't preserve the `callback_handler` setting from the original agent. This causes duplicate output when users set `callback_handler=None` to disable the default `PrintingCallbackHandler`.

## Problem

When a user creates a Strands agent with `callback_handler=None`:

```python
agent = Agent(
    model=model,
    tools=tools,
    system_prompt=system_prompt,
    callback_handler=None,  # Disable default PrintingCallbackHandler
)
agui_agent = StrandsAgent(agent, name="my-agent")
```

The `StrandsAgent` wrapper stores the agent's configuration but doesn't capture `callback_handler`. When it creates per-thread instances in the `run()` method, the new agents get the default `PrintingCallbackHandler`, causing duplicate output.

## Fix

Capture `callback_handler` from the original agent in `_agent_kwargs`:

```python
self._agent_kwargs = {
    "record_direct_tool_call": agent.record_direct_tool_call
    if hasattr(agent, "record_direct_tool_call")
    else True,
    # Preserve callback_handler setting to avoid duplicate output
    "callback_handler": getattr(agent, "callback_handler", None),
}
```

## Files Changed

- `ag_ui_strands/agent.py` - Add `callback_handler` to `_agent_kwargs` dict

## Testing

1. Create an agent with `callback_handler=None`
2. Wrap it in `StrandsAgent`
3. Run the agent and verify no duplicate output from `PrintingCallbackHandler`
