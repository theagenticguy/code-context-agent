---
title: "Refactor analysis pipeline to use Strands Swarm with shared context"
labels: ["enhancement", "architecture"]
area: "Agent behavior (prompts, calibration, orchestration)"
---

## Problem

The current analysis pipeline runs as a single monolithic agent that calls sub-agents via the Agents-as-Tools pattern (`feat/reasoning-amplification`). While this delivers deeper reasoning per-agent, the sub-agents are fire-and-forget with no shared context between them. The structure analyst's graph findings, the history analyst's coupling map, and the code reader's semantic analysis are passed back to the orchestrator as text — losing structured data along the way.

## Proposed solution

Replace the Agents-as-Tools pattern in `--full` mode with a **Strands Swarm** (`strands.multiagent.Swarm`). The Swarm provides:

### SharedContext accumulation
Each analyst agent writes structured findings to `SharedContext`, and the next agent reads them. The code reader gets the actual graph metrics dict, not a text summary.

```python
from strands.multiagent import Swarm

swarm = Swarm(
    nodes=[structure_analyst, history_analyst, code_reader, synthesizer],
    entry_point=structure_analyst,
    max_handoffs=10,
    execution_timeout=3600,  # full mode: 60 min
    hooks=[ReasoningCheckpointHook(), ...],
)
```

### Handoff-based coordination
Each agent calls `handoff_to_agent()` when done, passing context about what the next agent should focus on. The structure analyst hands off to history analyst with a list of hotspot files; the history analyst hands off to code reader with coupling pairs.

### Hook events for synthesis injection
Register `AfterNodeCallEvent` hooks to inject synthesis prompts between agent handoffs. After the structure analyst completes, inject: "Before the next agent runs, synthesize what the structural analysis revealed about architectural risks."

### Event streaming to TUI
The Swarm's `stream_async()` yields typed events per-node (`MultiAgentNodeStartEvent`, `MultiAgentNodeStreamEvent`, `MultiAgentNodeStopEvent`, `MultiAgentHandoffEvent`). These can be mapped to AG-UI events for the Rich TUI.

## Key changes required

| File | Change |
|------|--------|
| `agent/factory.py` | Create `Swarm` instead of single `Agent` for full mode |
| `agent/runner.py` | `_execute_analysis_stream()` must handle Swarm's `stream_async()` instead of single agent stream. Map multi-agent events to AG-UI events. |
| `agent/analysts.py` | Add `handoff_to_agent` awareness to sub-agent prompts. Structure shared context keys. |
| `agent/hooks.py` | Register `AfterNodeCallEvent` for synthesis injection between swarm nodes |
| `consumer.py` | Handle multi-agent event types in the TUI (show which sub-agent is running) |

## Swarm hook events available

| Event | Fired When | Writable Fields |
|-------|-----------|-----------------|
| `MultiAgentInitializedEvent` | Swarm construction complete | None |
| `BeforeNodeCallEvent` | Before each agent node executes | `cancel_node` (can cancel/interrupt) |
| `AfterNodeCallEvent` | After each agent node completes | None (read-only) |
| `BeforeMultiAgentInvocationEvent` | Before swarm execution starts | None |
| `AfterMultiAgentInvocationEvent` | After swarm execution completes | None |

## Alternatives considered

- **Agents-as-Tools** (current implementation): Simpler, works today, but no shared structured context between sub-agents. Each sub-agent's report is a text blob the orchestrator must re-parse.
- **GraphBuilder pipeline**: More explicit control flow than Swarm, but agents can't dynamically decide to hand off. The analysis pipeline benefits from some agent autonomy (e.g., the code reader might want to hand back to the structure analyst if it discovers unexpected patterns).
- **Swarm + GraphBuilder hybrid**: Use GraphBuilder for the fixed pipeline (structure -> history -> code -> synthesis) but allow Swarm-style handoffs within phases. Probably over-engineered for v1.

## Tenet alignment

- **The model picks the depth** — Swarm agents autonomously decide how deep to go and when to hand off
- **Layer signals, read less** — SharedContext accumulates structured signals across agents
- **Fail loud, fill gaps** — `BeforeNodeCallEvent` can cancel nodes that depend on failed predecessors
