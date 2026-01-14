# Code Context Agent - Tech Debt Remediation Plan

> **Generated:** 2026-01-14
> **Version Analyzed:** 0.2.0
> **Python:** 3.13+

---

## Executive Summary

This document provides a critical analysis of the code-context-agent codebase, identifying technical debt, performance risks, and improvement opportunities. The analysis is organized into phases for systematic remediation.

**Key Risk Areas:**
1. LSP server hangs and memory issues on large codebases
2. Unbounded subprocess execution and token explosion
3. Suboptimal prompt engineering for Claude 4.5 models
4. Tool descriptions lacking sufficient guidance
5. Code duplication and over-engineering in some areas

---

## Table of Contents

1. [Phase 1: Critical - Performance & Stability](#phase-1-critical---performance--stability)
2. [Phase 2: High Priority - Prompt Engineering](#phase-2-high-priority---prompt-engineering)
3. [Phase 3: Medium Priority - Tool Improvements](#phase-3-medium-priority---tool-improvements)
4. [Phase 4: Low Priority - Code Simplification](#phase-4-low-priority---code-simplification)
5. [Phase 5: Feature Roadmap](#phase-5-feature-roadmap)

---

## Phase 1: Critical - Performance & Stability

### 1.1 LSP Server Hangs and Memory Leaks

**Location:** `src/code_context_agent/tools/lsp/client.py:53-118`

**Problem:** The LSP client can hang or consume excessive memory:

1. **No startup timeout:** `start()` method has no timeout for initialization
2. **Pyright memory explosion:** If venv/node_modules accidentally included in workspace
3. **No graceful degradation:** Failures cascade to agent failure
4. **Reader task leak:** Background reader may not be cleaned up on errors

**Evidence from research:**
- Pyright issues #11181, #8670, #4941 document memory/hang problems
- Primary cause: Virtual environments treated as source code
- Secondary cause: No exclusion patterns configured

**Remediation:**

```python
# client.py - Add startup timeout and better error handling
async def start(
    self,
    server_cmd: list[str],
    workspace_path: str,
    startup_timeout: float = 30.0,  # NEW
    exclude_patterns: list[str] | None = None,  # NEW
) -> dict[str, Any]:
    """Start LSP server with bounded initialization."""
    try:
        self._process = await asyncio.wait_for(
            asyncio.create_subprocess_exec(...),
            timeout=startup_timeout
        )
    except asyncio.TimeoutError:
        raise RuntimeError(f"LSP server failed to start within {startup_timeout}s")
```

```python
# session.py - Add workspace configuration
def _get_workspace_config(self, workspace_path: str) -> dict:
    """Generate pyrightconfig.json to exclude problematic directories."""
    return {
        "exclude": [
            "**/.venv/**",
            "**/venv/**",
            "**/node_modules/**",
            "**/__pycache__/**",
            "**/dist/**",
            "**/build/**",
        ],
        "include": ["src", "lib", "app"],  # Prefer explicit includes
    }
```

**Config Enhancement:**

```python
# config.py - Add LSP-specific settings
lsp_startup_timeout: int = Field(
    default=30,
    ge=5,
    le=120,
    description="Maximum seconds to wait for LSP server to initialize"
)
lsp_max_files: int = Field(
    default=5000,
    ge=100,
    le=50000,
    description="Maximum files before LSP analysis is skipped"
)
```

---

### 1.2 Unbounded Subprocess Execution

**Location:** `src/code_context_agent/tools/discovery.py:19-68`

**Problem:** Shell commands can hang or produce token-explosion output:

1. **No input validation:** Command injection possible via `shell=True`
2. **Unbounded repomix:** Large repos can produce GB of output
3. **No progress feedback:** Long-running commands appear hung
4. **Hardcoded timeouts:** 120s/180s/300s may be insufficient or excessive

**Remediation:**

```python
# discovery.py - Add bounded execution with progress
import shlex
from typing import Callable

def _run_command(
    cmd: str | list[str],
    cwd: str | None = None,
    timeout: int = 120,
    max_output: int = 100_000,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, str | int]:
    """Run shell command with bounds and progress reporting."""

    # Prefer list form over shell=True
    if isinstance(cmd, str):
        cmd_list = shlex.split(cmd)
    else:
        cmd_list = cmd

    try:
        process = subprocess.Popen(
            cmd_list,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Stream output with timeout chunks
        stdout_parts = []
        total_len = 0

        while True:
            try:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break

                if total_len < max_output:
                    stdout_parts.append(line)
                    total_len += len(line)
                    if on_progress:
                        on_progress(f"Read {total_len} chars...")

            except subprocess.TimeoutExpired:
                process.kill()
                return {
                    "status": "error",
                    "stderr": f"Command timed out after {timeout}s",
                    "return_code": -1,
                }

        return {
            "status": "success" if process.returncode == 0 else "error",
            "stdout": "".join(stdout_parts),
            "stderr": process.stderr.read()[:10000],
            "return_code": process.returncode,
            "truncated": total_len >= max_output,
        }
```

**Repomix-specific bounds:**

```python
@tool
def repomix_orientation(
    repo_path: str,
    token_threshold: int = 300,
    max_file_count: int = 10000,  # NEW: Skip if repo too large
) -> str:
    """Generate orientation with safety bounds."""
    # Pre-check file count
    file_count_result = _run_command(
        f"rg --files '{repo_path}' | wc -l",
        timeout=10
    )
    file_count = int(file_count_result.get("stdout", "0").strip())

    if file_count > max_file_count:
        return json.dumps({
            "status": "skipped",
            "reason": f"Repository has {file_count} files (max: {max_file_count})",
            "recommendation": "Use --include patterns to limit scope"
        })
```

---

### 1.3 Agent Run Loop Infinite Hang

**Location:** `src/code_context_agent/agent/runner.py:106-114`

**Problem:** No maximum turn/time limit on agent execution:

```python
# Current: No bounds on agent iterations
async for event in agui_agent.run(input_data):
    await _dispatch_event(event, consumer)
```

**Remediation:**

```python
# runner.py - Add execution bounds
MAX_AGENT_TURNS = 100
MAX_AGENT_DURATION = 600  # 10 minutes

async def run_analysis(...) -> dict[str, Any]:
    start_time = time.monotonic()
    turn_count = 0

    try:
        async for event in agui_agent.run(input_data):
            turn_count += 1
            elapsed = time.monotonic() - start_time

            # Safety bounds
            if turn_count > MAX_AGENT_TURNS:
                logger.warning(f"Agent exceeded {MAX_AGENT_TURNS} turns, stopping")
                break
            if elapsed > MAX_AGENT_DURATION:
                logger.warning(f"Agent exceeded {MAX_AGENT_DURATION}s, stopping")
                break

            await _dispatch_event(event, consumer)
```

---

## Phase 2: High Priority - Prompt Engineering

### 2.1 System Prompt Optimization for Claude 4.5

**Location:** `src/code_context_agent/agent/sop.py`

**Current Issues:**

1. **Prompt too long:** ~4KB system prompt consumes context
2. **No structured output guidance:** Claude 4.5 Opus excels with explicit formats
3. **Temperature too high:** `temperature=1.0` adds unnecessary randomness
4. **Thinking budget suboptimal:** 10K tokens may be insufficient for deep analysis

**Best Practices for Claude 4.5 (from research):**

| Setting | Current | Recommended | Rationale |
|---------|---------|-------------|-----------|
| Temperature | 1.0 | 0.3-0.5 | Structured analysis needs consistency |
| Thinking Budget | 10K | 15-20K | Complex multi-phase analysis |
| System Prompt | 4KB+ | 2KB core + deferred | Progressive disclosure |
| Output Format | Free-form | JSON schema hints | Better tool coordination |

**Remediation:**

```python
# sop.py - Restructure prompts with progressive disclosure
CORE_CONSTRAINTS = """
## Core Rules (MUST FOLLOW)
1. NEVER run `tree` on repo root
2. Start with `create_file_manifest`
3. LSP via `lsp_start` then `lsp_*` tools
4. Evidence format: file:line + symbol + confidence
"""

FAST_MODE_PHASES = """
## FAST Mode Phases (10-15 tool calls)
0. Manifest: create_file_manifest
1. Orientation: repomix_orientation
2. Identity: rg_search for package.json/pyproject.toml
3. LSP: lsp_start, lsp_document_symbols on 3-5 files
4. Business: astgrep_scan_rule_pack
5. Bundle: write_file_list, repomix_bundle
6. Write: Generate CONTEXT.md
"""

# Deferred details - only included when agent asks
BUSINESS_LOGIC_DETAILED = """..."""  # Move detailed business logic guidance here
```

```python
# factory.py - Optimize model settings
def create_agent(mode: str = "fast") -> Agent:
    settings = get_settings()

    # Mode-specific settings
    if mode == "fast":
        temperature = 0.3
        thinking_budget = 8000
        model_id = settings.model_id or "anthropic.claude-sonnet-4-20250514-v1:0"
    else:  # deep
        temperature = 0.5
        thinking_budget = 20000
        model_id = settings.model_id or "global.anthropic.claude-opus-4-5-20251101-v1:0"

    model = BedrockModel(
        model_id=model_id,
        region_name=settings.region,
        temperature=temperature,
        additional_request_fields={
            "thinking": {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }
        },
    )
```

---

### 2.2 Tool Call Guidance

**Problem:** Agent may call tools inefficiently without clear guidance on:
- When to use parallel vs sequential calls
- Expected output sizes
- Error recovery strategies

**Remediation - Add meta-guidance:**

```python
# sop.py - Add tool coordination hints
TOOL_COORDINATION = """
## Tool Efficiency Rules

### Parallel-Safe Tools (call together):
- create_file_manifest + repomix_orientation
- Multiple rg_search with different patterns
- lsp_document_symbols on different files

### Sequential-Required Tools:
- lsp_start THEN lsp_* operations
- write_file_list THEN repomix_bundle
- create_file_manifest THEN any file operations

### Output Size Expectations:
| Tool | Typical Output | Max Safe |
|------|---------------|----------|
| create_file_manifest | 100-1000 files | 10K files |
| repomix_orientation | 5-50KB | 200KB |
| lsp_document_symbols | 1-10KB/file | 50KB/file |
| astgrep_scan | 10-100 matches | 500 matches |
| repomix_bundle | 50-500KB | 2MB |

### Error Recovery:
- LSP timeout: Skip file, note in output
- repomix failure: Use read_file_bounded fallback
- astgrep no matches: Expected for some repos
"""
```

---

## Phase 3: Medium Priority - Tool Improvements

### 3.1 Tool Description Enhancements

**Location:** `src/code_context_agent/tools/*.py`

**Issues:**
1. Descriptions lack "when NOT to use" guidance
2. Missing output size hints
3. No error examples

**Remediation Examples:**

```python
# discovery.py - Enhanced tool descriptions
@tool
def create_file_manifest(repo_path: str) -> str:
    """Create ignore-aware file manifest using ripgrep.

    USE THIS TOOL: As the FIRST step in any analysis workflow.

    DO NOT USE: If you already have a file list from a previous call.

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        JSON with:
        - manifest_path: Path to .agent/files.all.txt
        - file_count: Number of files found (typical: 100-5000)

    Output Size: ~50 bytes + ~50 bytes per file path

    Errors:
        - "rg not found": ripgrep not installed
        - Large file_count (>10K): Consider using --include patterns

    Example success:
        {"status": "success", "manifest_path": "/repo/.agent/files.all.txt", "file_count": 847}

    Example warning (large repo):
        {"status": "success", "file_count": 15000, "warning": "Large repository, consider filtering"}
    """
```

```python
# lsp/tools.py - Add more context
@tool
async def lsp_start(server_kind: str, workspace_path: str) -> str:
    """Start an LSP server for semantic code analysis.

    USE THIS TOOL: Before any lsp_document_symbols, lsp_hover, lsp_references calls.

    DO NOT USE:
    - If you already called lsp_start for this workspace
    - For repositories with >5000 files (may hang)
    - Without checking file count first

    Supported servers:
    - "ts": TypeScript/JavaScript (requires: typescript-language-server)
    - "py": Python (requires: pyright-langserver)

    Performance Notes:
    - Startup: 2-10 seconds typical
    - Memory: 200-500MB typical, can exceed 2GB on large repos
    - Hangs if: venv/node_modules included in workspace

    Args:
        server_kind: "ts" or "py"
        workspace_path: Absolute path to repo root

    Returns:
        JSON with session_id for subsequent calls

    Common Errors:
        - "LSP server failed to start": Server binary not found
        - Timeout: Repository too large or missing config
    """
```

---

### 3.2 ast-grep Rule Improvements

**Location:** `src/code_context_agent/rules/*.yml`

**Issues:**
1. Overly broad patterns causing false positives
2. Missing important patterns (GraphQL, gRPC)
3. No severity differentiation

**Remediation:**

```yaml
# py_business_logic.yml - Add more precise patterns
---
id: py-db-write-operation
language: Python
severity: error  # Higher severity for writes
message: "Database WRITE operation - critical business logic"
rule:
  any:
    - pattern: $SESSION.commit()
    - pattern: $SESSION.add($OBJ)
    - pattern: $OBJ.save()
    - pattern: $QUERYSET.create($$$)
    - pattern: $QUERYSET.update($$$)
    - pattern: $QUERYSET.delete()

---
id: py-auth-check
language: Python
severity: error
message: "Authorization/authentication check"
rule:
  any:
    - pattern: "@login_required"
    - pattern: "@permission_required($$$)"
    - pattern: "@require_role($$$)"
    - pattern: "if not $USER.is_authenticated"
    - pattern: "if not has_permission($$$)"

---
id: py-grpc-service
language: Python
severity: warning
message: "gRPC service method"
rule:
  pattern: |
    def $METHOD(self, request, context):
        $$$
constraints:
  METHOD:
    regex: "^[A-Z]"  # gRPC methods typically PascalCase
```

---

### 3.3 Input Validation

**Location:** All tool functions

**Issue:** No validation of user-controlled paths

```python
# tools/validation.py - NEW FILE
from pathlib import Path
import re

def validate_repo_path(path: str) -> Path:
    """Validate repository path is safe to use."""
    resolved = Path(path).resolve()

    # Prevent path traversal
    if ".." in str(resolved):
        raise ValueError(f"Path traversal detected: {path}")

    # Prevent system paths
    dangerous = ["/", "/etc", "/usr", "/var", "/home", "/root"]
    if str(resolved) in dangerous:
        raise ValueError(f"Dangerous path: {path}")

    # Must be directory
    if not resolved.is_dir():
        raise ValueError(f"Not a directory: {path}")

    return resolved

def validate_glob_pattern(pattern: str) -> str:
    """Validate glob pattern is safe."""
    # Prevent command injection via glob
    if re.search(r'[;&|`$]', pattern):
        raise ValueError(f"Invalid characters in pattern: {pattern}")
    return pattern
```

---

## Phase 4: Low Priority - Code Simplification

### 4.1 Eliminate Duplicate Code

**Issue:** `_run_command` and `_run_astgrep` are nearly identical

```python
# tools/shell.py - Unified command executor
def run_command(
    cmd: str | list[str],
    cwd: str | None = None,
    timeout: int = 120,
    max_output: int = 100_000,
    allowed_return_codes: tuple[int, ...] = (0,),
) -> CommandResult:
    """Unified shell command executor."""
    # Single implementation for all subprocess calls
```

```python
# discovery.py - Use shared executor
from .shell import run_command

@tool
def create_file_manifest(repo_path: str) -> str:
    result = run_command(
        ["rg", "--files"],
        cwd=repo_path,
        timeout=60,
    )
```

---

### 4.2 Simplify Consumer Pattern

**Issue:** Over-engineered for CLI-only output

**Current:** 4 files, 3 classes, complex event dispatch
**Needed:** Simple progress callback

```python
# consumer/simple.py - Simplified alternative
from typing import Callable, Protocol

class ProgressCallback(Protocol):
    def __call__(self, phase: str, message: str) -> None: ...

class SimpleConsumer:
    """Minimal consumer for CLI output."""

    def __init__(self, callback: ProgressCallback | None = None):
        self.callback = callback or self._default_callback

    def _default_callback(self, phase: str, message: str) -> None:
        from rich import print
        print(f"[dim]{phase}:[/dim] {message}")

    def on_tool(self, name: str) -> None:
        self.callback("tool", f"Running {name}...")

    def on_complete(self, path: str) -> None:
        self.callback("done", f"Output: {path}")
```

---

### 4.3 Session Manager Simplification

**Issue:** Singleton pattern with complex lifecycle for single-use sessions

```python
# lsp/session.py - Context manager pattern
from contextlib import asynccontextmanager

@asynccontextmanager
async def lsp_session(server_kind: str, workspace: str):
    """Simpler session management via context manager."""
    client = LspClient()
    try:
        await client.start(_get_server_cmd(server_kind), workspace)
        yield client
    finally:
        await client.shutdown()

# Usage in tools
async def lsp_start(server_kind: str, workspace_path: str) -> str:
    # Store in module-level dict instead of singleton class
    _sessions[f"{server_kind}:{workspace_path}"] = await LspClient().start(...)
```

---

### 4.4 JSON Response Simplification

**Issue:** Redundant JSON encode/decode in tool responses

```python
# Current pattern (verbose):
return json.dumps({
    "status": "success",
    "file": file_path,
    "symbols": symbols,
    "count": len(symbols),
})

# Simplified with dataclass:
from dataclasses import dataclass, asdict

@dataclass
class ToolResult:
    status: str
    data: dict

    def to_json(self) -> str:
        return json.dumps(asdict(self))

# Usage:
return ToolResult(status="success", data={"symbols": symbols}).to_json()
```

---

## Phase 5: Feature Roadmap

### 5.1 Short-term (1-2 sprints)

| Feature | Priority | Complexity | Description |
|---------|----------|------------|-------------|
| LSP timeout configuration | P0 | Low | Configurable timeouts via Settings |
| File count pre-check | P0 | Low | Skip analysis if repo too large |
| Progress streaming | P1 | Medium | Real-time updates during analysis |
| Parallel LSP queries | P1 | Medium | Batch symbol lookups |

### 5.2 Medium-term (3-4 sprints)

| Feature | Priority | Complexity | Description |
|---------|----------|------------|-------------|
| Multi-language LSP | P1 | Medium | Add Go (gopls), Rust (rust-analyzer) |
| Incremental analysis | P1 | High | Only re-analyze changed files |
| Result caching | P2 | Medium | Cache LSP results between runs |
| Custom rule packs | P2 | Low | User-provided ast-grep rules |
| Web UI consumer | P2 | High | Browser-based progress display |

### 5.3 Long-term (5+ sprints)

| Feature | Priority | Complexity | Description |
|---------|----------|------------|-------------|
| Watch mode | P2 | High | Continuous analysis with file watching |
| Remote analysis | P3 | High | Analyze repos via git URL |
| Plugin system | P3 | High | Custom tools and rules via plugins |
| Multi-repo analysis | P3 | High | Analyze monorepos with dependencies |
| AI-suggested rules | P3 | Very High | Generate ast-grep rules from examples |

---

## Appendix A: Dependency Analysis

### Current Dependencies (pyproject.toml)

| Package | Version | Risk | Notes |
|---------|---------|------|-------|
| strands-agents | >=1.22.0 | Low | Core SDK, actively maintained |
| strands-agents-tools | >=0.2.19 | Low | Shell tool included |
| ag-ui-strands | >=0.1.0 | Medium | Early version, API may change |
| ag-ui-protocol | >=0.1.10 | Medium | Event types dependency |
| cyclopts | >=4.4.5 | Low | Stable CLI framework |
| pydantic | >=2.12.5 | Low | Well-tested, stable |
| pydantic-settings | >=2.12.0 | Low | Env var handling |
| rich | >=14.0.0 | Low | Terminal rendering |
| networkx | >=3.6.1 | Low | Graph analysis (unused currently) |

### External Tool Dependencies

| Tool | Purpose | Installation | Risk |
|------|---------|--------------|------|
| ripgrep (rg) | File search | `apt install ripgrep` | Low |
| repomix | Context bundling | `npm i -g repomix` | Medium - npm dependency |
| ast-grep (sg) | Structural search | `pip install ast-grep-cli` | Low |
| pyright-langserver | Python LSP | `npm i -g pyright` | Medium - memory issues on large repos |
| typescript-language-server | TS/JS LSP | `npm i -g typescript-language-server` | Low |

---

## Appendix B: Quick Wins Checklist

- [ ] Add startup timeout to LSP client (1 hour)
- [ ] Add file count check before analysis (30 min)
- [ ] Lower default temperature to 0.3 (5 min)
- [ ] Add max_turns limit to run loop (30 min)
- [ ] Document tool output sizes in docstrings (2 hours)
- [ ] Merge duplicate _run_command functions (1 hour)
- [ ] Add pyrightconfig.json generation (1 hour)
- [ ] Add --max-files CLI option (30 min)

---

## Appendix C: Testing Recommendations

### Unit Tests Needed

1. **LSP client timeout handling** - Mock slow server
2. **Command execution bounds** - Verify truncation works
3. **Path validation** - Test traversal prevention
4. **Tool response format** - Validate JSON structure

### Integration Tests Needed

1. **Large repo handling** - Test with 10K+ file repos
2. **LSP session lifecycle** - Start, use, cleanup
3. **End-to-end FAST mode** - Complete workflow
4. **Error recovery** - Tool failures don't crash agent

### Suggested Test Repos

| Repo | Size | Purpose |
|------|------|---------|
| microsoft/vscode | ~50K files | Stress test, TS |
| django/django | ~5K files | Python, medium |
| expressjs/express | ~500 files | Small, JS |
| Your local monorepo | Varies | Real-world test |

---

*This document should be reviewed and updated quarterly as the codebase evolves.*
