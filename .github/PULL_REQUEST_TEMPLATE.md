## Summary

<!-- 1-3 sentences: what does this change and why? -->

## Area

<!-- Which subsystem(s) does this touch? Check all that apply. -->

- [ ] Discovery tools (ripgrep, repomix, file manifest)
- [ ] LSP tools (client, session manager, language servers)
- [ ] Graph tools (CodeGraph model, CodeAnalyzer, ProgressiveExplorer)
- [ ] Git tools (hotspots, blame, coupling, history)
- [ ] AST tools (ast-grep scanning, rule packs)
- [ ] Agent core (factory, runner, prompts, structured output)
- [ ] MCP server (FastMCP tools, resources, kickoff/poll)
- [ ] CLI (cyclopts commands, Rich TUI, AG-UI streaming)
- [ ] Config / models (pydantic-settings, output schema)
- [ ] CI / workflows
- [ ] Docs / templates

## Tenet check

<!-- Does this change align with the project tenets? Flag any tension. -->

- [ ] **Measure, don't guess** — rankings use graph metrics / git signals, not heuristics
- [ ] **Layer signals, read less** — combines multiple signal sources rather than deep-reading few files
- [ ] **Compress aggressively** — new output defends every token's presence
- [ ] **The model picks the depth** — no new user-facing knobs for things the model can decide
- [ ] **Machines read it first** — output is structured (tables, schemas, diagrams), not prose
- [ ] **Fail loud, fill gaps** — failures are surfaced, not swallowed silently

## Test plan

<!-- How was this tested? Check all that apply. -->

- [ ] `uv run pytest` — all tests pass
- [ ] New/updated unit tests for changed behavior
- [ ] Manual test against a real repository
- [ ] `uvx ruff check src/` and `uvx ruff format --check src/` clean
- [ ] `uvx ty check src/` clean
