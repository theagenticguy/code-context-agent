---
title: "v8: Index-first pipeline with Swarm specialists, kill AG-UI"
labels: ["enhancement", "architecture"]
area: "Agent behavior (prompts, calibration, orchestration)"
---

## Problem

The current agentic analysis produces a 62-node graph in 4 minutes. The deterministic indexer produces a 6,751-node graph in 30 seconds. The agent rebuilds what the indexer already computed, then skips the deep reasoning that justifies using an LLM at all.

Manual investigation with 3 parallel specialist agents (124 total tool calls, ~5 min each) produced dramatically richer analysis: exact coupling rates, bus factor risks, per-method invariant analysis, architectural epoch mapping, and actual bugs found in the code.

AG-UI adds complexity for no CI/CD value. The primary use case is `--quiet` with structured logs.

## Proposed Architecture: Three-Stage Pipeline

### Stage 1: `index` (deterministic, no LLM, ~30s)
Already implemented. LSP + AST-grep + git + framework detection → rich graph (6K+ nodes, 3K+ edges). Cacheable, CI-friendly.

### Stage 2: `analyze` (LLM Swarm, uses index as input, ~5-10 min)
**Replace the monolithic agent with a Strands Swarm.** Each specialist agent receives the pre-built index graph as context and runs its own deep investigation loop.

```python
from strands.multiagent import Swarm

# Load pre-built index
graph = load_graph(".code-context/code_graph.json")  # 6K+ nodes

# Specialist agents with focused tools + graph context
structure_analyst = Agent(
    system_prompt=f"...structural analysis...\nGraph context: {graph.summary()}",
    tools=[code_graph_analyze, lsp_*, astgrep_*, read_file_bounded],
)
history_analyst = Agent(
    system_prompt="...git history analysis...",
    tools=[git_hotspots, git_files_changed_together, git_blame_*, read_file_bounded],
)
code_reader = Agent(
    system_prompt="...deep code reading with structural context...",
    tools=[read_file_bounded, lsp_references, lsp_definition, rg_search],
)
synthesizer = Agent(
    system_prompt="...cross-signal synthesis → AnalysisResult + CONTEXT.md...",
    tools=[write_file, code_graph_analyze],
    structured_output_model=AnalysisResult,
)

swarm = Swarm(
    nodes=[structure_analyst, history_analyst, code_reader, synthesizer],
    entry_point=structure_analyst,
    max_handoffs=10,
    execution_timeout=600,
    hooks=[ReasoningCheckpointHook()],
)
```

**Why Swarm over Agents-as-Tools:**
- `SharedContext` passes structured data (not text blobs) between agents
- Each agent gets its own turn budget (40+ tool calls each)
- `handoff_to_agent` carries context about what to investigate next
- `AfterNodeCallEvent` hooks inject synthesis between agents
- Session persistence for long-running analyses

### Stage 3: Output
- `AnalysisResult` structured output from synthesizer agent
- CONTEXT.md, FILE_INDEX.md, business logic files
- `--quiet` mode: structured logs only (loguru/structlog)

## Kill AG-UI

AG-UI (`ag-ui-strands`, `StrandsAgent` wrapper) adds:
- A monkey-patched `__init__` in runner.py
- Event type translation overhead
- A dependency on `ag_ui` package

Replace with:
- **Interactive mode**: Rich TUI powered by strands `callback_handler` pattern + cyclopts
- **CI mode** (`--quiet`): Structured JSON logs via loguru/structlog, no TUI
- **Streaming**: Native strands `stream_async()` events, no AG-UI translation layer

## Quality Targets (from manual investigation baseline)

| Metric | Current (v7) | Target (v8) |
|--------|-------------|-------------|
| Graph input | Built from scratch (62 nodes) | Pre-built index (6K+ nodes) |
| Files deeply read | ~10 | 25+ |
| Tool calls total | ~35 | 100+ (across Swarm agents) |
| Coupling pairs | Mentioned vaguely | 7+ with exact co-change % |
| Bus factor analysis | None | Per-module ownership heatmap |
| Architectural timeline | None | Epoch mapping with commit velocity |
| Duration | 4 min (too fast, too shallow) | 5-10 min (deep, recursive) |
| Risks found | 5 surface-level | 8+ with root cause chains |

## Implementation Phases

### Phase 1: Index → Analyze integration
- `analyze` loads pre-built graph from `.code-context/code_graph.json`
- Graph summary injected into agent system prompt
- Graph query tools operate on the pre-built graph (not a new empty one)

### Phase 2: Swarm replacement
- Replace monolithic agent + Agents-as-Tools with Strands Swarm
- 4 specialist nodes with focused prompts and tool subsets
- SharedContext for structured data passing
- AfterNodeCallEvent hooks for synthesis injection

### Phase 3: Kill AG-UI
- Remove `ag_ui` dependency and `StrandsAgent` wrapper
- Native strands `callback_handler` for Rich TUI rendering
- Structured loguru/structlog output for `--quiet` mode
- Clean up runner.py (no more monkey-patching)

### Phase 4: CI/CD optimization
- `--quiet --json` for structured pipeline output
- Exit codes based on analysis quality thresholds
- Cacheable index with TTL-based invalidation
- GitHub Actions / GitLab CI integration examples

## Tenet alignment

- **Measure, don't guess** — Start from 6K+ node deterministic index, not LLM guesses
- **Layer signals, read less** — Swarm agents cross-reference graph + git + code reading
- **The model picks the depth** — Each Swarm agent decides how deep to go
- **Machines read it first** — Structured logs for CI/CD, not TUI
- **Fail loud, fill gaps** — AfterNodeCallEvent hooks catch shallow analysis
