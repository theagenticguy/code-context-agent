# ADR-0006: Security-Hardened Shell with Allowlist

**Date**: 2025-01-20

**Status**: accepted

## Context

The analysis agent needs limited shell access for operations that dedicated tools do not cover: custom git queries, file inspection commands, language tooling invocations, and analysis tool execution. However, an unrestricted shell in an AI agent is a significant security risk:

- The agent could execute arbitrary commands (network access, file deletion, system modification)
- Prompt injection in analyzed codebases could trick the agent into running malicious commands
- Shell operators (pipes, redirects, command chaining) expand the attack surface

The agent already has dedicated tools for most operations (ripgrep for search, read_file_bounded for reading, LSP for semantic analysis), so the shell tool only needs to fill gaps.

## Decision

Implement a security-hardened shell tool at `src/code_context_agent/tools/shell_tool.py` with three defense layers:

**1. Program allowlist (~50 read-only programs):**
```
ALLOWED_PROGRAMS: frozenset = {
    "ls", "find", "stat", "file", "du", "wc", "head", "tail", "cat",
    "grep", "rg", "ag", "awk", "sed", "jq", "yq",
    "git", "python", "node", "npx", "uv", "cargo", "go",
    "ast-grep", "repomix", "tree", "tokei", "cloc", "scc",
    ...
}
```

**2. Git subcommand restriction:**
```
GIT_READ_ONLY: frozenset = {
    "log", "diff", "show", "blame", "status", "branch", "tag",
    "rev-parse", "rev-list", "shortlog", "ls-files", "ls-tree",
    ...
}
```
Additionally, `git config` is only allowed with read flags (`--get`, `--list`, `--show-origin`).

**3. Dangerous pattern regex (`_DANGEROUS_RE`):**
Blocks shell operators (`; & |`), backtick substitution, `$()` expansion, `eval`, `exec`, `source`, dot-sourcing, and output redirection (`>`, `>>`).

**4. Sensitive path blocking:**
Access to `/etc`, `/root`, `/boot`, `/usr/sbin`, `/proc`, and `/sys` is denied.

Commands are executed via `subprocess.run(["sh", "-c", cmd])` with `capture_output=True`, a configurable timeout (default 900s), and output truncation at 100K characters.

## Consequences

**Positive:**

- Safe by default: even if the agent is tricked by prompt injection, it cannot execute destructive commands, access the network, or modify system files
- The allowlist is explicit and auditable; new programs require a conscious addition
- Git write operations (`push`, `commit`, `checkout`, `reset`) are blocked at the subcommand level
- Output truncation prevents memory exhaustion from commands that produce unbounded output

**Negative:**

- Requires allowlist updates when adding new CLI dependencies to the analysis pipeline (e.g., adding a new language tool)
- Shell operators are completely blocked, so multi-step shell pipelines (`cmd1 | cmd2`) are not possible; the agent must use multiple sequential shell calls
- The regex-based dangerous pattern detection is best-effort; novel encoding tricks could potentially bypass it (mitigated by the allowlist being the primary defense)

**Neutral:**

- The `ToolEfficiencyHook` in `hooks.py` warns when the agent uses shell for operations that have dedicated tools (e.g., `grep` instead of `rg_search`, `cat` instead of `read_file_bounded`)
- Commands run with `shell=True` via `sh -c` to support basic quoting and globbing, but dangerous operators are caught by the regex before execution
