# Security

code-context-agent runs a fully autonomous AI agent loop with filesystem access. Security is enforced through multiple layers: tool-level validation, shell hardening, CI scanning, and supply chain controls.

## Shell Tool Hardening

The `shell` tool is the primary attack surface. It enforces a program allowlist (read-only commands only), blocks all shell operators and redirects, restricts git to read-only subcommands, and prevents access to sensitive system directories.

!!! info
    See the full [Shell tool documentation](../tools/shell.md) for the complete allowlist, blocked operators, and examples.

## Input Validation

All tool inputs pass through validation functions in `src/code_context_agent/tools/validation.py`:

### `validate_repo_path`

- Rejects path traversal (`..` in path)
- Rejects dangerous system paths (`/`, `/etc`, `/usr`, `/var`, `/bin`, `/sbin`, `/root`, `/boot`)
- Requires the path to exist and be a directory

### `validate_file_path`

- Rejects path traversal (`..` in path)
- Optionally requires the file to exist
- Verifies the target is a file (not a directory)

### `validate_glob_pattern`

- Rejects command injection characters (`;`, `&`, `|`, `` ` ``, `$`, `(`, `)`, `{`, `}`, `\`)
- Rejects path traversal (`..` in pattern)

### `validate_path_within_repo`

- Resolves the path and verifies it is contained within the repository root
- Prevents path escape via symlinks or `..` after resolution

### `validate_search_pattern`

- Enforces a maximum pattern length (default 1000 characters)
- Validates regex syntax by compiling the pattern

## Path Traversal Prevention

Path traversal is blocked at multiple levels:

1. **Validation layer** -- `validate_repo_path` and `validate_file_path` reject any path containing `..`
2. **Repo containment** -- `validate_path_within_repo` ensures resolved paths stay within the repository root
3. **Shell layer** -- Sensitive system directories are blocked even if reached through allowed programs

## Supply Chain Security

- **Pinned npm dependencies** -- External tools like `jscpd` are invoked via `npx -y jscpd@4` with pinned major versions
- **Locked Python dependencies** -- `uv.lock` pins all transitive Python dependencies
- **License scanning** -- CI checks dependency licenses and blocks GPL-3.0, AGPL-3.0, and SSPL-1.0

## CI Security Pipeline

The project runs comprehensive security scanning in GitHub Actions:

| Scanner | What It Checks | Workflow |
|---------|----------------|----------|
| **CodeQL** | Semantic code analysis (Python) with security-extended queries | `codeql.yml` |
| **Semgrep** | OWASP Top 10 patterns and auto-detected rules | `security.yml` |
| **Bandit** | Python-specific security issues (hardcoded secrets, unsafe functions) | `security.yml` |
| **Gitleaks** | Secrets and credentials in git history | `security.yml` |
| **OSV-Scanner** | Known vulnerabilities in `uv.lock` dependencies | `security.yml` |
| **Trivy** | Filesystem scan for HIGH/CRITICAL vulnerabilities | `security.yml` |
| **Dependency Review** | PR-level dependency diff with license and vulnerability checks | `dependency-review.yml` |
| **OpenSSF Scorecard** | Supply chain security posture assessment | `scorecard.yml` |

All SAST scanners upload results in SARIF format for GitHub Security tab integration.

!!! warning
    The security CI pipeline runs on every push and PR to `main`. The `pre-push` git hook also runs Semgrep OWASP and Gitleaks locally before code reaches CI.

## SBOM Generation

A CycloneDX Software Bill of Materials is generated on every push and stored as a CI artifact for supply chain auditing.
