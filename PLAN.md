# Code Context Agent Implementation Plan

## Executive Summary

This plan describes the implementation of an AI agent that produces **narrated code context bundles** by combining:
- **bash automation** (rg/repomix/ast-grep) for safe file discovery and structural analysis
- **real LSP JSON-RPC over stdio** for semantic code understanding
- **LLM reasoning** to synthesize developer intent, conventions, and business logic

The agent defaults to **FAST mode** (quick overview) unless explicitly told to run **DEEP mode** (comprehensive analysis).

---

## Part 1: Design Analysis from Transcript

### 1.1 Core Philosophy

The transcript establishes a **progressive disclosure** approach:
1. Never run `tree` on repo root (token explosion)
2. Start with manifests and metadata, not contents
3. Use tools to *discover what matters*, then pack only that
4. LLM adds value by **inferring intent**, not just organizing output

### 1.2 The Seven Phases

| Phase | Name | Tools | Output |
|-------|------|-------|--------|
| 0 | Safe Discovery | `rg --files` | `.agent/files.all.txt` |
| 1 | Orientation | `repomix --no-files --token-count-tree` | `CONTEXT.orientation.md` |
| 2 | Identity + Entrypoints | `rg` patterns | `files.identity.txt`, `files.entrypoints.txt` |
| 3 | LSP Semantic Truth | JSON-RPC over stdio | `files.lsp_cone.txt`, symbol index |
| 4 | Business Logic Mining | ast-grep + LSP fan-in | `files.business.txt`, ranked candidates |
| 5 | Tests + Docs | `rg` + LSP hover | `files.tests.txt`, docstring cache |
| 6 | Curated Bundle | `repomix --stdin` | `CONTEXT.bundle.md` |
| 7 | Narrated Output | LLM synthesis | `CONTEXT.md` (final deliverable) |

### 1.3 FAST vs DEEP Mode

**FAST Mode (default)**
- Tool budget: ~10-15 tool calls
- LSP: entrypoints only, 3-5 symbol fan-in checks
- Business logic: 5-15 candidates
- Output: single `CONTEXT.md` + 2 appendices

**DEEP Mode (on request)**
- Tool budget: ~50+ tool calls
- LSP: 2-4 hop dependency cones
- Business logic: 20-50 candidates with full ranking
- Test mapping via LSP references
- Output: multiple bundles + detailed change playbooks

### 1.4 Business Logic Definition

**Treat as business logic when code:**
- Reads/writes domain data (DB, repositories, ORMs)
- Enforces rules (validation, authorization, eligibility, pricing)
- Orchestrates workflows (multi-step: create -> validate -> persist -> notify)
- Integrates externally where domain decisions occur

**NOT business logic (plumbing):**
- Framework bootstrapping, DI wiring, routing tables
- Logging/tracing/metrics boilerplate
- Config parsing, env wiring
- Generic utilities without domain invariants

### 1.5 Evidence-Based Inference Contract

Every LLM inference must follow:
```
Hypothesis -> Evidence Anchors -> Confidence (High/Med/Low) -> Implications
```

Evidence anchors are concrete: file path + line range, symbol names, test names.

---

## Part 2: Strands Agents Architecture

### 2.1 Key SDK Patterns (from Context7 documentation)

**Tool Creation:**
```python
from strands import Agent, tool

@tool
def my_tool(param: str) -> str:
    """Tool description becomes the model's understanding.

    Args:
        param: Description used by model to understand parameter
    """
    return result
```

**Agent Initialization:**
```python
from strands import Agent
from strands.models import BedrockModel

model = BedrockModel(
    model_id="anthropic.claude-sonnet-4-20250514-v1:0",
    region_name="us-west-2",
    temperature=0.2,
)

agent = Agent(
    model=model,
    tools=[tool1, tool2, tool3],
    system_prompt="Your SOP here..."
)

response = agent("User task description")
```

**Parallel vs Sequential Execution:**
```python
from strands.tools.executors import SequentialToolExecutor

# Default: concurrent execution for independent tools
agent = Agent(tools=[weather_tool, time_tool])

# Sequential: when tools have dependencies
agent = Agent(
    tool_executor=SequentialToolExecutor(),
    tools=[screenshot_tool, email_tool]
)
```

### 2.2 Tool Design Strategy

The LLM should be able to:

**a) Reason and select tools:**
- Tools have clear, distinct purposes via docstrings
- Tool names are verb-noun (e.g., `scan_files`, `query_lsp_symbols`)
- Docstrings explain *when* to use, not just *what* it does

**b) Reason over combined outputs:**
- Tool outputs are structured (JSON where possible)
- Outputs include metadata (file paths, line numbers, confidence)
- Agent synthesizes across multiple tool results

**c) Use parallel tool calling:**
- Independent discovery tools run concurrently (rg, repomix orientation)
- LSP queries can batch multiple files
- ast-grep rules run in single pass
- Sequential only where needed (e.g., repomix pack after file list built)

### 2.3 Recommended Tool Architecture

```
tools/
  shell.py          # Wrapper around strands_tools.shell with bounds
  lsp/
    __init__.py
    client.py       # LSP JSON-RPC framing over stdio
    tools.py        # @tool wrappers for lsp_start, lsp_symbols, etc.
  astgrep/
    __init__.py
    rules.py        # Rule pack definitions
    tools.py        # @tool wrapper for ast-grep scan
  discovery/
    __init__.py
    tools.py        # rg_files, rg_search, repomix_orientation
```

---

## Part 3: Custom Tools Specification

### 3.1 Shell Tool (Bounded Execution)

```python
@tool
def run_shell(cmd: str, cwd: str | None = None, max_lines: int = 1000) -> str:
    """Execute a shell command with bounded output.

    Use for: rg, repomix, ast-grep CLI commands.
    Do NOT use for: interactive commands, unbounded output.

    Args:
        cmd: Shell command to execute (non-interactive)
        cwd: Working directory (defaults to repo root)
        max_lines: Maximum output lines (truncates with warning)

    Returns:
        Command stdout (truncated if exceeds max_lines)
    """
```

### 3.2 LSP Tools (JSON-RPC over stdio)

```python
@tool
def lsp_start(server_kind: str, workspace_path: str) -> str:
    """Start an LSP server over stdio and initialize workspace.

    Supported servers:
    - "ts": typescript-language-server --stdio
    - "py": pyright-langserver --stdio

    Args:
        server_kind: "ts" or "py"
        workspace_path: Absolute path to workspace root

    Returns:
        session_id for subsequent LSP calls
    """

@tool
def lsp_document_symbols(session_id: str, file_path: str) -> str:
    """Get document symbol outline (functions, classes, methods).

    Requires: file opened via lsp_open first.

    Args:
        session_id: From lsp_start
        file_path: Absolute path to file

    Returns:
        JSON array of DocumentSymbol objects
    """

@tool
def lsp_hover(session_id: str, file_path: str, line: int, character: int) -> str:
    """Get hover information (docstrings, JSDoc, type info).

    Args:
        session_id: From lsp_start
        file_path: Absolute path
        line: 0-indexed line number
        character: 0-indexed column

    Returns:
        JSON with hover contents (often includes documentation)
    """

@tool
def lsp_references(session_id: str, file_path: str, line: int, character: int) -> str:
    """Find all references to symbol at position (fan-in analysis).

    Args:
        session_id: From lsp_start
        file_path: Absolute path
        line: 0-indexed line number
        character: 0-indexed column

    Returns:
        JSON array of Location objects {uri, range}
    """

@tool
def lsp_definition(session_id: str, file_path: str, line: int, character: int) -> str:
    """Go to definition of symbol at position.

    Args:
        session_id: From lsp_start
        file_path: Absolute path
        line: 0-indexed line number
        character: 0-indexed column

    Returns:
        JSON array of Location objects
    """
```

### 3.3 ast-grep Tool

```python
@tool
def astgrep_scan(
    language: str,
    rule_pack: str,
    include_globs: list[str],
    exclude_globs: list[str] | None = None,
    cwd: str | None = None,
) -> str:
    """Run ast-grep structural search with predefined rule pack.

    Rule packs available:
    - "ts_business_logic": DB calls, state mutations, API calls in TS/JS
    - "py_business_logic": DB calls, state mutations, HTTP calls in Python
    - "ts_routes": HTTP route/handler definitions
    - "py_routes": Flask/FastAPI route definitions

    Args:
        language: "ts" | "py" | "tsx" | "jsx"
        rule_pack: Name of predefined rule pack
        include_globs: Paths to include (e.g., ["src/**", "apps/**"])
        exclude_globs: Paths to exclude (e.g., ["**/node_modules/**"])
        cwd: Working directory

    Returns:
        JSON stream (newline-delimited) of matches with file, range, rule_id
    """
```

### 3.4 Discovery Tools

```python
@tool
def create_file_manifest(repo_path: str) -> str:
    """Create ignore-aware file manifest using ripgrep.

    Respects .gitignore, skips hidden/binary files.
    Writes to .agent/files.all.txt

    Args:
        repo_path: Repository root path

    Returns:
        Path to manifest file + file count
    """

@tool
def repomix_orientation(repo_path: str, token_threshold: int = 300) -> str:
    """Generate token-aware orientation snapshot (no file contents).

    Produces CONTEXT.orientation.md with:
    - Directory structure
    - Token distribution tree
    - Identity file list

    Args:
        repo_path: Repository root
        token_threshold: Minimum tokens to show in tree

    Returns:
        Path to orientation file
    """

@tool
def repomix_bundle(file_list_path: str, output_path: str, compress: bool = True) -> str:
    """Pack curated files into markdown bundle.

    Uses --stdin to pack only specified files.

    Args:
        file_list_path: Path to file containing paths to pack (one per line)
        output_path: Output markdown file path
        compress: Use tree-sitter compression

    Returns:
        Path to bundle + token count
    """
```

---

## Part 4: System Prompt / SOP

### 4.1 Operating Constraints Block

```markdown
## Operating Constraints (MUST FOLLOW)

1. NEVER run `tree` on repository root
2. Start with `rg --files` manifest (ignore-aware, safe)
3. All shell commands must be:
   - Non-interactive
   - Bounded output (use head/max-count/max_lines)
   - Scoped with globs
4. Use repomix --no-files first (metadata only)
5. Only pack code via repomix --stdin with curated file list
6. LSP must use JSON-RPC over stdio with Content-Length framing
7. Every inference MUST be: Hypothesis -> Evidence -> Confidence -> Implications
```

### 4.2 Phase Instructions (FAST Mode)

```markdown
## FAST Mode Workflow (DEFAULT)

Execute phases in order. Use parallel tool calls where dependencies allow.

### Phase 0: Manifest
- Run: create_file_manifest(repo_path)
- Output: .agent/files.all.txt

### Phase 1: Orientation
- Run: repomix_orientation(repo_path)
- Output: CONTEXT.orientation.md

### Phase 2: Identity + Entrypoints
- Read identity files: package.json, pyproject.toml, tsconfig.json, etc.
- Run entrypoint search: rg patterns for main/server/app.listen/etc.
- Output: files.identity.txt, files.entrypoints.txt

### Phase 3: LSP Semantic Pass (MINIMAL)
- Start LSP server for detected language(s)
- For each entrypoint (max 5):
  - lsp_open
  - lsp_document_symbols (get outline)
  - lsp_hover on top 2-3 symbols (get docs)
- For 3-5 central symbols:
  - lsp_references (estimate fan-in)
  - lsp_definition (1 hop)
- Output: files.lsp_cone.txt, symbol_index notes

### Phase 4: Business Logic Mining
- Run: astgrep_scan with ts_business_logic or py_business_logic
- From matches, identify 5-15 candidates by:
  - Proximity to data (DB calls)
  - Branching density
  - Domain vocabulary
  - Fan-in (from LSP refs)
- For each candidate write:
  - Hypothesis (1-2 sentences)
  - Evidence anchors (file:line, symbol names)
  - Confidence (High/Med/Low)
- Output: files.business.txt, business_logic_index

### Phase 5: Tests + Docs (QUICK)
- rg for test patterns in test directories
- Note which tests reference business logic candidates
- Output: files.tests.txt

### Phase 6: Curated Bundle
- Merge file lists: identity + entrypoints + lsp_cone + business + tests
- Run: repomix_bundle(merged_list)
- Output: CONTEXT.bundle.md

### Phase 7: Write CONTEXT.md
Include sections:
1. Executive Summary (what repo does, who it serves)
2. How to Run/Test/Build (from identity files)
3. Architecture Map (modules, boundaries, dependencies)
4. Key Flows (request lifecycle, job lifecycle)
5. Business Logic Index (ranked, with evidence)
6. Conventions & Style (naming, layering, error handling)
7. Risks & Hotspots (complex files, unclear areas)
8. Appendix links: CONTEXT.orientation.md, CONTEXT.bundle.md
```

### 4.3 Business Logic Focus Block

```markdown
## Business Logic Focus (REQUIRED)

### Definition
Business logic = domain rules + decisions + transformations.

Treat code as business logic when it:
- Touches domain data (DB calls, repositories, SQL, transactions)
- Enforces rules (validation/authz/eligibility/pricing/limits/state transitions)
- Orchestrates multi-step workflows (create -> validate -> persist -> notify)
- Integrates externally where domain decisions occur (payments/billing/identity)

Do NOT label pure plumbing as business logic.

### Ranking Criteria
Prioritize items with:
1. High fan-in (LSP references count)
2. DB write paths
3. Branching density
4. Domain vocabulary in names/docs
5. Test coverage

### Evidence Requirement
For each business logic item, document:
- Name + Role (rule/workflow/data access/integration)
- Evidence anchors (file:line, concrete calls)
- Inputs/outputs (from signature/types/docs)
- Rules/invariants (explicit + inferred)
- Confidence level
- Tests that cover it
```

---

## Part 5: ast-grep Rule Packs

### 5.1 TypeScript/JavaScript Business Logic Rules

```yaml
# rules/ts_business_logic.yml

id: ts-db-method-call
language: TypeScript
message: "Potential DB interaction via method call"
severity: warning
rule:
  pattern: $OBJ.$METHOD($$ARGS)
constraints:
  METHOD:
    regex: "^(query|execute|transaction|beginTransaction|commit|rollback|select|insert|update|delete|upsert|save|create|destroy|remove|bulkCreate|aggregate|count|find(One|Many)?|findUnique|findFirst|findById|where)$"
---
id: ts-sql-tagged-template
language: TypeScript
message: "Potential raw SQL via tagged template"
severity: warning
rule:
  any:
    - pattern: sql`$$SQL`
    - pattern: SQL`$$SQL`
    - pattern: db.sql`$$SQL`
---
id: ts-state-mutation-member-assign
language: TypeScript
message: "Potential state/status mutation via member assignment"
severity: warning
rule:
  pattern: $OBJ.$FIELD = $VAL
constraints:
  FIELD:
    regex: "^(status|state|phase|stage|lifecycle|enabled|active|deleted|archived|approved|paid|shipped|role|tier|plan)$"
---
id: ts-state-transition-call
language: TypeScript
message: "Potential state transition via method call"
severity: warning
rule:
  pattern: $OBJ.$METHOD($$ARGS)
constraints:
  METHOD:
    regex: "^(setState|setStatus|transition|transitionTo|advance|approve|reject|cancel|refund|activate|deactivate|archive|restore|markPaid|markShipped)$"
---
id: ts-external-api-call
language: TypeScript
message: "Potential external API interaction"
severity: warning
rule:
  any:
    - pattern: fetch($$ARGS)
    - pattern: axios.$METHOD($$ARGS)
    - pattern: $CLIENT.request($$ARGS)
```

### 5.2 Python Business Logic Rules

```yaml
# rules/py_business_logic.yml

id: py-db-method-call
language: Python
message: "Potential DB interaction via method call"
severity: warning
rule:
  pattern: $OBJ.$METHOD($$ARGS)
constraints:
  METHOD:
    regex: "^(execute|executemany|query|select|insert|update|delete|commit|rollback|flush|add|add_all|merge|save|save_all|upsert|begin|transaction)$"
---
id: py-state-mutation-attr-assign
language: Python
message: "Potential state/status mutation"
severity: warning
rule:
  pattern: $OBJ.$FIELD = $VAL
constraints:
  FIELD:
    regex: "^(status|state|phase|stage|lifecycle|enabled|active|deleted|archived|approved|paid|shipped|role|tier|plan)$"
---
id: py-external-http-requests
language: Python
message: "Potential external API interaction"
severity: warning
rule:
  pattern: requests.$METHOD($$ARGS)
constraints:
  METHOD:
    regex: "^(get|post|put|patch|delete|request)$"
```

---

## Part 6: LSP Fan-in + Tests Collector

### 6.1 Algorithm

```python
def collect_fan_in_and_tests(
    session_id: str,
    candidate_files: list[str],
    lsp_client: LspClient,
    max_symbols_per_file: int = 30,
) -> list[SymbolStats]:
    """
    For each candidate file:
    1. Get document symbols
    2. Flatten to candidate symbols (functions/classes/methods)
    3. Score by business-domain vocabulary
    4. For top symbols, call references
    5. Compute fan-in (unique referencing files) and test hits
    """
    results = []

    for file_path in candidate_files:
        symbols = lsp_client.document_symbols(session_id, file_path)
        symbols = flatten_symbols(symbols)
        symbols = sorted(symbols, key=business_name_score, reverse=True)
        symbols = symbols[:max_symbols_per_file]

        for sym in symbols:
            refs = lsp_client.references(
                session_id, file_path,
                sym.selection_range.start.line,
                sym.selection_range.start.character
            )

            ref_files = [uri_to_path(r.uri) for r in refs]
            unique_files = set(ref_files)
            test_files = [f for f in unique_files if is_test_file(f)]

            results.append(SymbolStats(
                file=file_path,
                name=sym.name,
                kind=sym.kind,
                fan_in=len(unique_files),
                test_coverage=len(test_files),
                test_examples=test_files[:5]
            ))

    # Sort by fan-in + test coverage
    return sorted(results, key=lambda x: (x.fan_in, x.test_coverage), reverse=True)
```

### 6.2 Test File Detection Regex

```python
TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__)(/|$)|"
    r"(\.test\.)|"
    r"(_test\.py$)|"
    r"(^|/)test_.*\.py$",
    re.IGNORECASE
)

def is_test_file(path: str) -> bool:
    return bool(TEST_PATH_RE.search(path))
```

---

## Part 7: Project Structure

```
code-context-agent/
├── pyproject.toml              # Already configured with strands-agents
├── AGENTS.md                   # Developer tools guide
├── PLAN.md                     # This file
├── src/
│   └── code_context_agent/
│       ├── __init__.py
│       ├── cli.py              # Entry point (extend with analyze command)
│       ├── config.py           # Settings (extend with agent config)
│       ├── display.py          # Rich output
│       │
│       ├── agent/              # NEW: Agent orchestration
│       │   ├── __init__.py
│       │   ├── sop.py          # System prompts for FAST/DEEP modes
│       │   ├── workflow.py     # Main agent workflow driver
│       │   └── models.py       # Pydantic models for structured output
│       │
│       ├── tools/              # NEW: Custom @tool definitions
│       │   ├── __init__.py
│       │   ├── shell.py        # Bounded shell execution
│       │   ├── discovery.py    # rg manifest, repomix tools
│       │   ├── astgrep.py      # ast-grep scan wrapper
│       │   └── lsp/
│       │       ├── __init__.py
│       │       ├── client.py   # LSP JSON-RPC framing over stdio
│       │       ├── session.py  # Session management
│       │       └── tools.py    # @tool wrappers
│       │
│       └── rules/              # NEW: ast-grep rule packs
│           ├── __init__.py
│           ├── ts_business_logic.yml
│           └── py_business_logic.yml
│
└── tests/
    ├── test_tools/
    │   ├── test_shell.py
    │   ├── test_discovery.py
    │   └── test_lsp.py
    └── test_agent/
        └── test_workflow.py
```

---

## Part 8: Implementation Steps

### Step 1: LSP Client Module
Create `src/code_context_agent/tools/lsp/client.py`:
- Implement JSON-RPC framing (Content-Length headers)
- Session management (start/stop servers)
- Request/response correlation
- Timeout handling

### Step 2: LSP Tools
Create `src/code_context_agent/tools/lsp/tools.py`:
- `lsp_start`, `lsp_open`, `lsp_shutdown`
- `lsp_document_symbols`, `lsp_hover`
- `lsp_definition`, `lsp_references`

### Step 3: Shell Tool
Create `src/code_context_agent/tools/shell.py`:
- Bounded execution wrapper
- Output truncation with warning

### Step 4: Discovery Tools
Create `src/code_context_agent/tools/discovery.py`:
- `create_file_manifest`
- `repomix_orientation`
- `repomix_bundle`

### Step 5: ast-grep Tools
Create `src/code_context_agent/tools/astgrep.py`:
- Rule pack loader from YAML files
- `astgrep_scan` with streaming JSON parsing

### Step 6: SOP Prompts
Create `src/code_context_agent/agent/sop.py`:
- FAST_MODE_SOP
- DEEP_MODE_SOP
- BUSINESS_LOGIC_FOCUS block
- OPERATING_CONSTRAINTS block

### Step 7: Workflow Driver
Create `src/code_context_agent/agent/workflow.py`:
- Agent initialization with tools
- Mode selection (fast/deep)
- Output file writing

### Step 8: CLI Integration
Extend `src/code_context_agent/cli.py`:
- Add `analyze` command with `--deep` flag
- Add `--output-dir` option

### Step 9: Tests
- Unit tests for LSP client (mock subprocess)
- Integration tests for tool outputs
- Agent workflow smoke tests

---

## Part 9: Dependencies Update

Add to `pyproject.toml` if not present:
```toml
dependencies = [
    # Existing
    "strands-agents>=1.22.0",
    "strands-agents-tools>=0.2.19",
    "pydantic>=2.12.5",
    "pydantic-settings>=2.12.0",
    "rich>=14.0.0",
    "cyclopts>=4.4.5",

    # May need for advanced features
    "networkx>=3.6.1",  # Already present - for dependency graphs
]
```

External tools required (not Python packages):
- `ripgrep` (rg) - file manifest, content search
- `repomix` - context bundling (npm install -g repomix)
- `ast-grep` (sg) - structural search
- `typescript-language-server` - for TS/JS LSP
- `pyright` (pyright-langserver) - for Python LSP

---

## Part 10: Success Criteria

### FAST Mode (<2 minutes on typical repo)
- [ ] Creates CONTEXT.md with all required sections
- [ ] Business logic index has 5-15 ranked items
- [ ] Each item has evidence anchors + confidence
- [ ] CONTEXT.bundle.md contains curated code only
- [ ] Token count reasonable (<100k for medium repo)

### DEEP Mode (5-15 minutes)
- [ ] Extended dependency cones captured
- [ ] Test-to-business mapping complete
- [ ] Change playbooks included
- [ ] Architecture smells documented

### Quality Metrics
- [ ] No hallucinated file paths (all evidence verifiable)
- [ ] Confidence levels correlate with evidence density
- [ ] Business logic vs plumbing correctly distinguished
- [ ] Parallel tool calls used where safe
