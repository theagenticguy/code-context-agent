# Analysis Pipeline Specification

> Global spec documenting the 10-phase analysis pipeline, deterministic index mode, mode variants, and prompt architecture in code-context-agent v7.1.0.
> Last updated: 2026-03-22

## Purpose

Define the 10-phase analysis pipeline executed by the Strands Agent, the deterministic index mode (LLM-free pipeline), per-phase tool usage, mode-specific variants (standard, full, focus, incremental), the Jinja2 prompt architecture, graph algorithm catalog, and output constraints. This spec is the authoritative reference for what the agent does during analysis.

## Pipeline Overview

| Phase | Name | Tools | Output |
|-------|------|-------|--------|
| 1 | Foundation | create_file_manifest, repomix_orientation, repomix_compressed_signatures | files.all.txt, CONTEXT.orientation.md, CONTEXT.signatures.md |
| 2 | Identity | read_file_bounded, rg_search | Project metadata (package.json, pyproject.toml, README) |
| 3 | Semantic Discovery | lsp_start, lsp_document_symbols, lsp_references, lsp_definition, lsp_hover, lsp_workspace_symbols, lsp_diagnostics, lsp_shutdown | Symbol maps, reference chains, type info |
| 4 | Pattern Discovery | astgrep_scan, astgrep_scan_rule_pack, astgrep_inline_rule | Business logic patterns, code smell matches |
| 5 | Git History | git_hotspots, git_files_changed_together, git_blame_summary, git_file_history, git_contributors, git_recent_commits, git_diff_file | Churn data, coupling, ownership |
| 6 | Graph Analysis | code_graph_create, code_graph_ingest_* (7), code_graph_analyze, code_graph_explore, code_graph_export, code_graph_save | code_graph.json, structural metrics |
| 6.5 | Deep Read | read_file_bounded | Source comprehension of key files |
| 7 | Business Logic | write_file_list, rg_search | files.business.txt, ranked items |
| 8 | Tests and Health | rg_search, detect_clones, astgrep_scan_rule_pack, code_graph_ingest_clones, code_graph_analyze | Test map, health metrics, refactoring candidates |
| 9 | Bundle | repomix_bundle, repomix_bundle_with_context, repomix_split_bundle, code_graph_save | CONTEXT.bundle.md |
| 10 | Write Context | write_file | CONTEXT.md (<=300 lines) |

## Phase Details

### Phase 1: Foundation (parallel)
Three tools establish the baseline:
1. `create_file_manifest(repo_path)` -- rg --files, produces files.all.txt
2. `repomix_orientation(repo_path)` -- Token-aware structure snapshot
3. `repomix_compressed_signatures(repo_path)` -- Optional Tree-sitter API surface

Auto-skip: repomix_orientation skips if >10,000 files.

### Phase 2: Identity
Read project metadata (package.json, pyproject.toml, README.md). Search entrypoints via rg_search.

### Phase 3: Semantic Discovery
1. lsp_start must succeed (Critical Tool Failure if not)
2. lsp_document_symbols on entrypoint files
3. lsp_references for central symbols
4. lsp_definition to trace dependency chains
5. lsp_workspace_symbols for cross-workspace search
6. lsp_diagnostics for type errors in key files

Fallback chain: if primary LSP returns empty, _try_fallback_session() tries next server.

### Phase 4: Pattern Discovery
Rule packs: py_business_logic, ts_business_logic, py_code_smells, ts_code_smells.
Ad-hoc astgrep_scan for repo-specific patterns.

### Phase 5: Git History
git_hotspots (churn), git_files_changed_together (coupling), git_blame_summary (ownership), git_recent_commits, git_contributors.

### Phase 6: Graph Analysis
Build multi-layer graph, run algorithms (hotspots, foundations, trust, modules, entry_points, triangles, unused_symbols, refactoring), explore progressively, export mermaid, persist JSON.

### Phase 6.5: Deep Read
Mode-variant file reading:
- **Standard**: Top 10 by hotspot/PageRank, multi-signal priority
- **Full**: ALL business logic files, paginate completely
- **Focus**: Top 10 in focus area + direct dependents
- **Incremental**: Changed files + callers

### Phase 7: Business Logic Ranking
Combine betweenness centrality, PageRank, AST-grep severity, and git churn. Write files.business.txt.

### Phase 8: Tests and Health
Test pattern search, clone detection (jscpd), code smell scanning, unused symbol detection, refactoring candidate ranking.

### Phase 9: Bundle
write_file_list + repomix_bundle. Variants: compressed signatures, git-aware, split, JSON export.

### Phase 10: Write Context
CONTEXT.md structure (<=300 lines): Summary, Quick Start, Architecture (mermaid <=15 nodes), Key Flow (sequence diagram), Business Logic (ranked table), Files, Conventions, Risks.

## Mode Variants

| Mode | Phase 1 | Phase 6.5 | Hooks | Limits |
|------|---------|-----------|-------|--------|
| standard | Full | Top 10 files | OutputQuality, ToolEfficiency | 1000 turns, 1200s |
| full | Full | ALL files | + FailFast | 3000 turns, 3600s |
| focus | Full | Top 10 in area | OutputQuality, ToolEfficiency | 1000 turns, 1200s |
| incremental | Skipped | Changed + callers | OutputQuality, ToolEfficiency | 1000 turns, 1200s |

## Prompt Architecture

System prompt rendered from Jinja2 templates in `templates/`.

```
templates/
  system.md.j2                    -- Main entry, includes all partials
  partials/
    _rules.md.j2                  -- Analysis rules
    _astgrep.md.j2                -- AST-grep usage
    _code_graph.md.j2             -- Graph usage
    _git_history.md.j2            -- Git usage
    _output_format.md.j2          -- Output formatting
    _business_logic.md.j2         -- Ranking guide
    _reasoning.md.j2              -- Structural reasoning triggers
  steering/
    _size_limits.md.j2            -- Standard mode budget
    _full_mode.md.j2              -- Full mode relaxed limits
    _conciseness.md.j2            -- Brevity
    _anti_patterns.md.j2          -- What to avoid
    _tool_efficiency.md.j2        -- Tool selection
    _graph_exploration.md.j2      -- Graph strategy
```

Mode-conditional rendering: full modes include _full_mode.md.j2, others include _size_limits.md.j2.

## Deterministic Index Mode

The `index` CLI command provides an LLM-free alternative to the full analysis pipeline. It builds a structural code graph without any Bedrock API calls, making it faster and cheaper.

### Index vs. Analyze Layering

```
index (fast, deterministic, LLM-free)
  |-- File manifest (rg or fallback)
  |-- LSP symbols per file
  |-- AST-grep rule packs
  |-- Git hotspots + co-changes
  |-- Clone detection
  |-- Output: code_graph.json only
  |
  v (optional)
analyze (full LLM pipeline, 10 phases)
  |-- Loads existing graph if present (index → analyze)
  |-- LLM-driven deep read, business logic ranking
  |-- Narrated CONTEXT.md, bundles, orientation
  |-- Output: full .code-context/ artifact set
```

The index mode covers steps equivalent to Phases 1, 3, 4, 5 (partial), and 6 of the full pipeline but without LLM steering or narration. The resulting graph can be:
- Queried via MCP tools (`query_code_graph`, `explore_code_graph`)
- Visualized via the `viz` command
- Used as a foundation for a subsequent `analyze --since` incremental run

### Index Pipeline Steps

| Step | Tool | Graceful Failure |
|------|------|-----------------|
| 1. File manifest | `rg --files` | Falls back to `Path.rglob` |
| 2. Language detection | Extension mapping | Always succeeds |
| 3. LSP symbols | Per-language LSP server | Skips language if server unavailable |
| 4. AST-grep patterns | Rule packs per language | Skips if `ast-grep` not installed |
| 5. Git hotspots | `git log` analysis | Skips if not a git repo |
| 6. Git co-changes | Per-hotspot co-change | Skips on failure |
| 7. Clone detection | `jscpd` via npx | Skips if `npx` not installed |
| 8. Save graph | JSON serialization | Required (will error if write fails) |

## Graph Algorithms

| Algorithm | Method | NetworkX Function | Edge Types | Returns |
|-----------|--------|-------------------|------------|---------|
| hotspots | find_hotspots | betweenness_centrality | calls, references | Ranked list |
| foundations | find_foundations | pagerank | calls, imports | Ranked list |
| trust | find_trusted_foundations | pagerank (personalized) | calls, imports | Ranked list |
| entry_points | find_entry_points | in/out_degree + framework boost | calls | Sorted list |
| modules | detect_modules | leiden/louvain_communities | calls, imports | Clusters |
| triangles | find_triangles | enumerate_all_cliques | calls, imports | Triads |
| similar | get_similar_nodes | pagerank (personalized) | all | Ranked list |
| coupling | calculate_coupling | shortest_path_length | all | Metrics |
| dependencies | get_dependency_chain | single_source_shortest_path_length | calls, imports | BFS tree |
| unused_symbols | find_unused_symbols | predecessor filter | references, calls, imports | Symbol list |
| refactoring | find_refactoring_candidates | composite | all | Ranked candidates |
| clusters_by_pattern | find_clusters_by_pattern | node filter | all | Grouped matches |
| clusters_by_category | find_clusters_by_category | node filter | all | Categorized matches |
| blast_radius | blast_radius | BFS with confidence decay | calls, references, imports | Impact scores |
| flows | trace_execution_flows | DFS from entry points | calls | Named paths |
| diff_impact | diff_impact | Line-overlap mapping + blast_radius | all | Affected nodes + test suggestions |

## Requirements

### Requirement: The analysis pipeline SHALL produce required artifacts
Every successful analysis run MUST produce a minimum set of output files.

#### Scenario: Standard analysis completes
- **WHEN** analysis runs to completion in standard mode
- **THEN** these files exist: files.all.txt, CONTEXT.orientation.md, CONTEXT.bundle.md, CONTEXT.md, code_graph.json

#### Scenario: Analysis fails early
- **WHEN** analysis encounters a fatal error before Phase 10
- **THEN** partial artifacts may exist but CONTEXT.md may not be generated

### Requirement: Phase progression SHALL be tracked via tool-to-phase mapping
TOOL_PHASE_MAP in consumer/phases.py MUST map each tool name to its AnalysisPhase.

#### Scenario: lsp_start tool is called
- **WHEN** the agent calls lsp_start
- **THEN** the consumer transitions to Phase 3 (Semantic Discovery) in the TUI

#### Scenario: write_file tool is called
- **WHEN** the agent calls write_file
- **THEN** the consumer transitions to Phase 10 (Write Context) in the TUI

### Requirement: CONTEXT.md SHALL respect size limits in standard mode
The system prompt and exit gate MUST enforce output constraints.

#### Scenario: Standard mode output
- **WHEN** analysis completes in standard mode
- **THEN** CONTEXT.md is <=300 lines with mermaid diagrams <=15 nodes

#### Scenario: Full mode output
- **WHEN** analysis completes in full mode
- **THEN** CONTEXT.md size limits are relaxed per steering/_full_mode.md.j2

### Requirement: Incremental mode SHALL preserve the existing graph
Incremental mode MUST load the existing graph and only re-ingest changed files.

#### Scenario: Incremental analysis with existing graph
- **WHEN** analysis runs with --since flag and .code-context/code_graph.json exists
- **THEN** the existing graph is loaded via code_graph_load and only changed files are re-ingested

#### Scenario: Incremental skips Phase 1
- **WHEN** analysis runs in incremental mode
- **THEN** Phase 1 (Foundation) is skipped entirely per prompt instructions

### Requirement: Full mode SHALL enable FailFastHook
Full mode MUST use strict error handling to surface tool failures immediately.

#### Scenario: Tool error in full mode
- **WHEN** a non-exempt tool returns {"status": "error"} in full mode
- **THEN** FailFastHook raises FullModeToolError, halting analysis immediately

#### Scenario: Exempt tool error in full mode
- **WHEN** rg_search returns {"status": "error"} in full mode
- **THEN** analysis continues (rg_search is in the exempt list)

### Requirement: Graph analysis SHALL use multi-signal ranking for business logic
Phase 7 MUST combine multiple signals to rank business logic items.

#### Scenario: Business logic ranking
- **WHEN** the agent ranks business logic items in Phase 7
- **THEN** ranking combines betweenness centrality, PageRank, AST-grep severity, and git churn

#### Scenario: Hotspot with no AST-grep match
- **WHEN** a file has high betweenness centrality but no AST-grep pattern match
- **THEN** it can still rank highly based on graph metrics and git churn alone

### Requirement: Prompt architecture SHALL use mode-conditional Jinja2 includes
The system prompt template MUST render different steering content based on analysis mode.

#### Scenario: Standard mode prompt
- **WHEN** get_prompt(mode="standard") is called
- **THEN** the rendered prompt includes steering/_size_limits.md.j2

#### Scenario: Full mode prompt
- **WHEN** get_prompt(mode="full") is called
- **THEN** the rendered prompt includes steering/_full_mode.md.j2 instead of _size_limits.md.j2

### Requirement: The agent SHALL verify exit gate before completion
The agent MUST verify all required outputs before signaling completion.

#### Scenario: All artifacts present
- **WHEN** the agent reaches the exit gate
- **THEN** it verifies: files.all.txt, files.business.txt, CONTEXT.orientation.md, CONTEXT.bundle.md, CONTEXT.md exist and CONTEXT.md is <=300 lines

### Requirement: The deterministic index SHALL produce a valid graph without LLM calls
The index pipeline MUST build a code_graph.json using only deterministic tools.

#### Scenario: Index a Python repository
- **WHEN** `build_index(repo_path)` is called on a Python repository with rg, ty, and ast-grep available
- **THEN** a code_graph.json is written containing LSP-derived nodes/edges, AST-grep pattern matches, git hotspots, and clone data

#### Scenario: Index with missing tools
- **WHEN** `build_index(repo_path)` is called and ast-grep is not installed
- **THEN** Steps 1-3, 5-7 complete successfully; Step 4 (AST-grep) is skipped with a warning

#### Scenario: Index as foundation for incremental analysis
- **WHEN** `build_index(repo_path)` is run, then `analyze --since HEAD~3` is run on the same repo
- **THEN** the analyze command loads the existing graph from code_graph.json and only re-analyzes changed files

### Requirement: Entry point detection SHALL incorporate framework patterns
The `find_entry_points` algorithm MUST use framework detection to boost scores for known entry point patterns.

#### Scenario: FastAPI project
- **WHEN** `find_entry_points` runs on a repo where `detect_frameworks` finds "fastapi"
- **THEN** functions matching `@(app|router).(get|post|put|delete|patch)` patterns receive a 3.0x entry point boost

#### Scenario: Multiple frameworks
- **WHEN** a repo contains both Next.js pages and pytest test files
- **THEN** patterns from both "nextjs" and "pytest" framework definitions are applied with their respective boosts
