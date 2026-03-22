# ADR-0005: LSP Fallback Chains

**Date**: 2025-02-15

**Status**: accepted

## Context

The agent uses Language Server Protocol (LSP) for semantic code analysis: document symbols, references, definitions, hover information, and workspace-wide symbol search. LSP servers vary significantly in reliability and feature completeness:

- **ty** (`ty server`): Fast Python type checker, good for symbols and diagnostics, but newer and may not handle all edge cases
- **pyright** (`pyright-langserver --stdio`): Mature Python LSP, comprehensive but slower to start
- **typescript-language-server**: Stable for TypeScript/JavaScript but requires `tsconfig.json`
- **rust-analyzer**, **gopls**, **jdtls**: Language-specific servers with varying feature sets

A single LSP server per language is insufficient because:
1. Servers may fail to start (missing binary, incompatible project layout)
2. Servers may return empty results for valid queries (indexing incomplete, unsupported features)
3. Different servers have different strengths (ty is faster, pyright is more comprehensive)

## Decision

Implement ordered fallback chains per language, configured in `Settings.lsp_servers` (`src/code_context_agent/config.py`):

```python
lsp_servers: dict[str, list[str]] = {
    "py": ["ty server", "pyright-langserver --stdio"],
    "ts": ["typescript-language-server --stdio"],
    "rust": ["rust-analyzer"],
    "go": ["gopls serve"],
    "java": ["jdtls"],
}
```

Fallback operates at two levels:

1. **Startup fallback** (in `LspSessionManager.get_or_create`): If the primary server fails to start (binary not found, timeout, crash), try the next server in the chain.

2. **Result-level fallback** (in `_try_fallback_session` at `src/code_context_agent/tools/lsp/tools.py`): If the primary server starts successfully but returns empty results for `document_symbols`, try the next server. The fallback session is cached under a `{kind}-fallback:{workspace}` key so subsequent calls reuse it.

The `lsp_start` tool normalizes server kinds with an alias map (`"typescript" -> "ts"`, `"python" -> "py"`) and returns a session ID in `kind:workspace` format for all subsequent LSP operations.

## Consequences

**Positive:**

- Better coverage: ty handles most Python files quickly; pyright catches the rest
- Graceful degradation: if a server binary is missing, analysis continues with the next option rather than failing
- Result-level fallback is transparent to the agent; the tool response includes `fallback_used: true` and the actual `server` name used
- Configurable via `CODE_CONTEXT_LSP_SERVERS` environment variable (JSON dict)

**Negative:**

- Startup latency from failed attempts: if ty fails, the agent waits up to `lsp_startup_timeout` (30s default) before trying pyright
- Two LSP server processes may run simultaneously (primary + fallback) consuming 200-1000MB combined memory
- The fallback session accesses private `_sessions` and `_server_commands` dicts on the session manager, creating implicit coupling

**Neutral:**

- Fallback chains are only meaningful for languages with multiple configured servers; single-server languages (ts, rust, go, java) get no benefit
- Adding a new language requires adding it to `Settings.lsp_servers` and optionally installing the corresponding LSP binary
