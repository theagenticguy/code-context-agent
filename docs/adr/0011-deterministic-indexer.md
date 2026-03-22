# ADR-0011: Deterministic Indexer

**Date**: 2026-03-22

**Status**: accepted

## Context

The primary analysis mode (`code-context-agent analyze`) runs a full AI agent loop: the LLM decides which tools to call, explores the codebase interactively, and produces a narrative analysis with risk assessments and business logic summaries. This takes 5-20 minutes and consumes LLM tokens proportional to codebase size.

Many use cases only need the structural code graph (modules, classes, functions, their relationships) without the narrative layer. Examples:

- **CI pipelines** that want a dependency graph for impact analysis
- **MCP server bootstrapping** where the graph is the primary artifact
- **Rapid re-indexing** after code changes without waiting for a full AI analysis
- **Cost-sensitive environments** where LLM token spend must be minimized

Alternatives considered:

- **Cached AI analysis**: Run the full analysis once and cache the graph. But the graph becomes stale as code changes, and re-running the full analysis just to update the graph is wasteful.
- **Lightweight AI mode**: Use a cheaper/faster model for graph-only analysis. Still costs tokens and introduces model-specific behavior differences.
- **External static analysis tools**: Tools like `pyan`, `depend`, or `madge` generate dependency graphs, but each covers a single language and none integrate with the existing `CodeGraph` model.

## Decision

Add a new `code-context-agent index` command that builds the code graph deterministically using only static analysis tools — no LLM involved.

Key design choices:

- **Calls adapter functions directly**, not `@tool` wrappers — avoids the overhead of tool dispatch, JSON serialization, and the agent loop. Adapter functions are the underlying implementations that tools delegate to.
- **Four data sources**: LSP (document symbols, references, definitions), AST-grep (pattern matching for framework-specific constructs), git (hotspots, co-change coupling), and clone detection (duplicate code regions)
- **All external tools are optional** with graceful fallbacks — if `ast-grep` is not installed, those analysis phases are skipped rather than failing. The indexer produces the best graph it can with available tools.
- **Output is a `CodeGraph`** in the same format as the AI analysis produces, so downstream consumers (MCP server, visualization, export) work identically regardless of how the graph was built
- **Auto-registers** in the multi-repo registry (ADR-0010) after successful indexing

## Consequences

**Positive:**

- Sub-minute indexing for most repos (seconds for small repos, under a minute for large ones)
- Zero token cost — no LLM invocation at all
- Deterministic and reproducible — same code always produces the same graph
- Composable with AI analysis: run `index` for the structural graph, then optionally run `analyze` to layer on narrative insights and risk assessments
- CI-friendly: fast, predictable, no API keys required beyond what the static tools need

**Negative:**

- Less complete than AI analysis: no narrative documentation, no risk assessment, no business logic summaries, no architectural pattern identification
- Cannot discover implicit relationships that require reasoning (e.g., a function that is only connected to another through a message queue or event bus)
- Quality depends on LSP server availability and accuracy for the target language

**Neutral:**

- The `index` and `analyze` commands share the same `CodeGraph` model and output format, so they are interchangeable from the perspective of downstream tools
- Graceful fallbacks mean the graph may vary in completeness depending on which external tools are installed
