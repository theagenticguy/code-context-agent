# Data Model Specification

> Global spec documenting Pydantic models, code graph model, graph storage backends, and structured output schema in code-context-agent v7.1.0.
> Last updated: 2026-03-22

## Purpose

Define all Pydantic models (base classes, structured output, event models), the CodeGraph model (nodes, edges, types, algorithms), the configuration model, and output artifacts. This spec is the authoritative reference for every data structure in the system.

## Base Models

Defined in `models/base.py`. All project models inherit from one of these:

| Base | Frozen | Extra | Use Case |
|------|--------|-------|----------|
| `FrozenModel` | Yes | forbid | Immutable data transfer: output models, graph nodes/edges |
| `StrictModel` | No | forbid | Mutable internal state: phase tracking, analysis state |

Both validate assignments. StrictModel strips whitespace from strings.

## Structured Output: AnalysisResult

Defined in `models/output.py`. Set via `structured_output_model=AnalysisResult` in the Agent constructor.

```
AnalysisResult (FrozenModel)
  |-- status: str                          # "completed", "partial", "failed"
  |-- summary: str                         # 2-3 sentence executive summary
  |-- total_files_analyzed: int            # File count in repository
  |-- analysis_mode: str                   # "standard" or "full"
  |-- business_logic_items: list[BusinessLogicItem]
  |-- risks: list[ArchitecturalRisk]
  |-- generated_files: list[GeneratedFile]
  |-- graph_stats: GraphStats | None
  |-- refactoring_candidates: list[RefactoringCandidate]
  |-- code_health: CodeHealthMetrics | None
  |-- phase_timings: list[PhaseTimingItem]
```

### Sub-Models

**BusinessLogicItem:** rank (int), name (str), role (str), location (str, e.g. src/auth.py:42), score (float 0-1), category (str|None: db, auth, validation, workflows, integrations)

**ArchitecturalRisk:** description (str), severity (str: high/medium/low), location (str|None), mitigation (str|None)

**GeneratedFile:** path (str), line_count (int>=0), description (str)

**RefactoringCandidate:** type (Literal: extract_helper, inline_wrapper, dead_code, code_smell), pattern (str), files (list[str]), occurrence_count (int>=1), duplicated_lines (int>=0), score (float>=0)

**CodeHealthMetrics:** duplication_percentage (float 0-100), total_clone_groups (int>=0), unused_symbol_count (int>=0), code_smell_count (int>=0)

**GraphStats:** node_count (int>=0), edge_count (int>=0), module_count (int>=0), hotspot_count (int>=0)

**PhaseTimingItem:** phase (int 1-10), name (str), duration_seconds (float>=0), tool_count (int>=0)

## Code Graph Model

Defined in `tools/graph/model.py`. Wraps a NetworkX `MultiDiGraph`.

### Node Types (NodeType enum)

| Value | Description | LSP SymbolKind mapping |
|-------|-------------|----------------------|
| file | Source file | 1 |
| class | Class definition | 5, 23 (Struct) |
| function | Function definition | 12, 9 (Constructor) |
| method | Method definition | 6 |
| variable | Variable/constant | 13, 14 |
| module | Module/namespace | 2 |
| pattern_match | AST-grep match | N/A (from astgrep ingest) |

### Edge Types (EdgeType enum)

| Value | Description | Ingest Source |
|-------|-------------|---------------|
| calls | Function/method call | LSP references |
| imports | Module import | LSP definitions |
| references | Symbol reference | LSP references |
| contains | Containment (file->function) | LSP document symbols |
| inherits | Class inheritance | Inheritance ingest |
| implements | Interface implementation | Inheritance ingest |
| tests | Test -> production coverage | Test ingest |
| cochanges | Files changed together | Git coupling ingest |
| similar_to | Cloned/duplicated code | Clone detection ingest |

### CodeNode (FrozenModel)

| Field | Type | Description |
|-------|------|-------------|
| id | str | "file_path:symbol_name" or "file_path:line" |
| name | str | Human-readable display name |
| node_type | NodeType | Classification enum |
| file_path | str | Absolute path to source file |
| line_start | int | Starting line (0-indexed) |
| line_end | int | Ending line (0-indexed) |
| metadata | dict | Extensible: docstring, visibility, rule_id, category, note |

### CodeEdge (FrozenModel)

| Field | Type | Description |
|-------|------|-------------|
| source | str | Source node ID |
| target | str | Target node ID |
| edge_type | EdgeType | Relationship classification |
| weight | float | Edge weight for algorithms (default 1.0) |
| confidence | float | Source reliability score (0.0-1.0, default 1.0) |
| metadata | dict | Extensible: line number, context |

#### Edge Confidence Values by Source

Confidence scores indicate how reliable the edge data source is. Higher values mean greater certainty that the relationship exists in reality.

| Source | Confidence | Rationale |
|--------|------------|-----------|
| LSP (symbols, references, definitions) | 0.95 | Compiler-grade type resolution |
| Inheritance ingest | 0.85 | Structural relationship from AST |
| Clone detection (similar_to) | 0.75 | Token-level similarity heuristic |
| Test-production mapping (tests) | 0.70 | Name-based heuristic matching |
| Git co-change (cochanges) | 0.60 | Statistical correlation, not causal |

Confidence is factored into graph algorithms. For example, `blast_radius` decays impact per hop using the formula: `impact = 1 / (2^distance) * confidence_product`, where `confidence_product` is the product of edge confidences along the path. The `get_view()` method aggregates parallel edges by taking the max confidence.

### CodeGraph Class

Non-Pydantic class wrapping `nx.MultiDiGraph`. Key methods:

| Method | Returns | Description |
|--------|---------|-------------|
| `add_node(CodeNode)` | None | Add node with flattened attributes |
| `add_edge(CodeEdge)` | None | Add edge keyed by edge_type.value |
| `get_view(edge_types?)` | nx.DiGraph | Filtered simple graph for algorithms |
| `get_nodes_by_type(NodeType)` | list[str] | Filter nodes by type |
| `get_edges_by_type(EdgeType)` | list[tuple] | Filter edges by type |
| `to_node_link_data()` | dict | JSON-serializable export |
| `from_node_link_data(dict)` | CodeGraph | Reconstruct from JSON (handles old/new nx format) |
| `describe()` | dict | Summary: counts, type distributions, density |

## Graph Storage

Defined in `tools/graph/storage.py`. A `GraphStorage` protocol allows pluggable backends.

### GraphStorage Protocol

```
GraphStorage (Protocol, runtime_checkable)
  |-- add_node(CodeNode) -> None
  |-- add_edge(CodeEdge) -> None
  |-- has_node(str) -> bool
  |-- get_node_data(str) -> dict | None
  |-- get_nodes_by_type(NodeType) -> list[str]
  |-- get_edges_by_type(EdgeType) -> list[tuple]
  |-- node_count() -> int
  |-- edge_count() -> int
  |-- to_node_link_data() -> dict
  |-- describe() -> dict
```

### NetworkXStorage (default)

In-memory backend wrapping `CodeGraph`. Delegates all operations to the underlying `nx.MultiDiGraph`. Selected when `CODE_CONTEXT_GRAPH_BACKEND=networkx` (default).

### KuzuStorage (persistent)

KuzuDB-backed persistent graph storage. Selected when `CODE_CONTEXT_GRAPH_BACKEND=kuzu`. Stores the graph in a KuzuDB database directory (`<repo>/.code-context/graph.kuzu`) for persistence across sessions.

| Feature | Details |
|---------|---------|
| Schema | `CodeNode` node table (id PK, name, node_type, file_path, line_start, line_end, metadata), `CodeEdge` rel table (edge_type, weight, confidence, metadata) |
| Cypher queries | `execute_cypher(query)` for read-only queries (CREATE/DELETE/SET/MERGE/DROP/ALTER blocked) |
| NetworkX compat | `_to_networkx()` converts to `nx.MultiDiGraph` for algorithm compatibility |
| CodeGraph compat | `to_code_graph()` converts to `CodeGraph` for existing tool integration |

Backend selection is configured via `Settings.graph_backend` (`CODE_CONTEXT_GRAPH_BACKEND` env var).

## Configuration Model

Defined in `config.py::Settings(BaseSettings)`. Env prefix: `CODE_CONTEXT_`.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| model_id | str | global.anthropic.claude-opus-4-6-v1 | Bedrock model |
| region | str | us-east-1 | AWS region |
| temperature | float | 1.0 | Must be 1.0 for adaptive thinking |
| lsp_servers | dict[str, list[str]] | {py: [ty, pyright], ...} | Ordered fallback chains |
| lsp_timeout | int | 30 | LSP operation timeout (5-300s) |
| lsp_startup_timeout | int | 30 | LSP init timeout (5-120s) |
| lsp_max_files | int | 5000 | Skip LSP above this (100-50000) |
| agent_max_turns | int | 1000 | Standard mode turn limit (10-5000) |
| agent_max_duration | int | 1200 | Standard mode time limit (60-7200s) |
| full_max_duration | int | 3600 | Full mode time limit (300-14400s) |
| full_max_turns | int | 3000 | Full mode turn limit (100-10000) |
| context7_enabled | bool | true | Enable context7 MCP |
| graph_backend | str | networkx | Graph storage: 'networkx' (in-memory) or 'kuzu' (persistent KuzuDB) |
| otel_disabled | bool | true | Disable OpenTelemetry |

## Output Artifacts

| File | Format | Description |
|------|--------|-------------|
| .code-context/CONTEXT.md | Markdown | Narrated architecture overview (<=300 lines) |
| .code-context/CONTEXT.orientation.md | Markdown | Token distribution tree |
| .code-context/CONTEXT.signatures.md | Markdown | Compressed Tree-sitter signatures |
| .code-context/CONTEXT.bundle.md | Markdown | Curated source code pack |
| .code-context/code_graph.json | JSON | NetworkX node-link format graph |
| .code-context/analysis_result.json | JSON | Serialized AnalysisResult |
| .code-context/files.all.txt | Text | Complete file manifest |
| .code-context/files.business.txt | Text | Ranked business logic files |
| .code-context/structure.json | JSON | repomix JSON metadata export |

## Requirements

### Requirement: AnalysisResult SHALL be the single structured output model
The Strands Agent MUST be configured with structured_output_model=AnalysisResult.

#### Scenario: Agent completes analysis
- **WHEN** the Strands Agent finishes execution
- **THEN** it returns an AnalysisResult with status, summary, business_logic_items, risks, and graph_stats

#### Scenario: Agent partially completes
- **WHEN** the agent is stopped due to turn/time limits
- **THEN** it returns an AnalysisResult with status="partial" and whatever data was gathered

### Requirement: CodeGraph SHALL support multiple edge types between same node pair
The underlying MultiDiGraph MUST allow parallel edges with different keys.

#### Scenario: Two nodes connected by calls and references
- **WHEN** node A calls node B and also references node B
- **THEN** both edges coexist in the MultiDiGraph, and `get_view()` aggregates their weights

#### Scenario: Filtered view for algorithms
- **WHEN** `get_view([EdgeType.CALLS, EdgeType.IMPORTS])` is called
- **THEN** only calls and imports edges appear in the returned DiGraph, weights aggregated

### Requirement: FrozenModel instances SHALL be immutable after creation
FrozenModel MUST use Pydantic's frozen=True config.

#### Scenario: Attempt to modify a CodeNode field
- **WHEN** code tries to set `node.name = "new_name"` on a FrozenModel instance
- **THEN** Pydantic raises a validation error

#### Scenario: Attempt to modify AnalysisResult
- **WHEN** code tries to set `result.status = "failed"` after creation
- **THEN** Pydantic raises a validation error

### Requirement: Graph serialization SHALL handle both old and new NetworkX formats
The system MUST support both pre-3.6 ("links") and 3.6+ ("edges") NetworkX node-link formats.

#### Scenario: Loading a graph saved by NetworkX before 3.6
- **WHEN** `from_node_link_data` receives data with "links" key instead of "edges"
- **THEN** it passes `edges="links"` to `nx.node_link_graph` for backward compatibility

#### Scenario: Loading a graph saved by NetworkX 3.6 or later
- **WHEN** `from_node_link_data` receives data with "edges" key
- **THEN** it uses the default `nx.node_link_graph` behavior

### Requirement: Settings SHALL be cached as a singleton
`get_settings()` MUST use `@lru_cache(maxsize=1)` to return the same instance.

#### Scenario: Multiple calls to get_settings
- **WHEN** `get_settings()` is called multiple times
- **THEN** the same Settings instance is returned each time

#### Scenario: Test needs fresh settings
- **WHEN** a test needs to override settings
- **THEN** it calls `get_settings.cache_clear()` before constructing a new Settings

### Requirement: All output models SHALL use Field constraints
Numeric fields MUST use ge/le/gt/lt constraints. String fields MUST use descriptions.

#### Scenario: BusinessLogicItem with invalid score
- **WHEN** a BusinessLogicItem is created with score=1.5
- **THEN** Pydantic validation raises an error (score must be 0.0-1.0)

#### Scenario: PhaseTimingItem with invalid phase
- **WHEN** a PhaseTimingItem is created with phase=11
- **THEN** Pydantic validation raises an error (phase must be 1-10)

### Requirement: CodeEdge SHALL carry a confidence score
Every CodeEdge MUST have a confidence field (0.0-1.0) reflecting source reliability.

#### Scenario: LSP-derived edge
- **WHEN** an edge is created from LSP references or definitions
- **THEN** its confidence is 0.95

#### Scenario: Git co-change edge
- **WHEN** an edge is created from git co-change analysis
- **THEN** its confidence is 0.60

#### Scenario: Confidence used in algorithms
- **WHEN** blast_radius computes impact through a path with mixed-confidence edges
- **THEN** the cumulative confidence (product of per-hop confidences) attenuates the impact score

### Requirement: GraphStorage SHALL support pluggable backends
The system MUST support both NetworkX (in-memory) and KuzuDB (persistent) backends via the GraphStorage protocol.

#### Scenario: Default backend
- **WHEN** `CODE_CONTEXT_GRAPH_BACKEND` is not set or is "networkx"
- **THEN** `NetworkXStorage` is used (in-memory, default)

#### Scenario: KuzuDB backend
- **WHEN** `CODE_CONTEXT_GRAPH_BACKEND=kuzu`
- **THEN** `KuzuStorage` is used with database at `<repo>/.code-context/graph.kuzu`

#### Scenario: KuzuDB Cypher queries
- **WHEN** `execute_cypher("MATCH (n:CodeNode) RETURN n.id")` is called on KuzuStorage
- **THEN** results are returned as a list of rows

#### Scenario: KuzuDB write protection
- **WHEN** `execute_cypher("DELETE (n:CodeNode)")` is called on KuzuStorage
- **THEN** a ValueError is raised (write operations blocked)
