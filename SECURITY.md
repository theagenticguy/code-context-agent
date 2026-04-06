# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |
| < 1.0   | No        |

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

To report a vulnerability, use [GitHub Security Advisories](https://github.com/theagenticguy/code-context-agent/security/advisories/new) to privately disclose the issue.

You can expect:

- **Acknowledgment** within 48 hours
- **Status update** within 7 days with an assessment and timeline
- **Fix or mitigation** released as a patch version

## Security Model

code-context-agent runs locally and executes shell commands (`rg`, `ast-grep`, `repomix`, LSP servers) against the target repository. It does not:

- Send source code to external services (Bedrock API calls contain prompts and tool results, not raw files)
- Write to the analyzed repository (read-only analysis)
- Require network access beyond AWS Bedrock and optional context7 MCP

### Shell execution

The `shell` tool executes commands via `subprocess` with configurable allowlists. The tool validates commands against a sensitive-directory blocklist and token-path patterns before execution.

### Dependency security

- Dependencies are pinned via `uv.lock` and audited by OSV-Scanner, Trivy, Grype, and uv audit in CI
- GitHub Actions are pinned to commit SHAs to prevent supply chain attacks
- Betterleaks scans for leaked secrets on every push

## Security Scanning

| Layer | Tool | What It Checks | Trigger |
|-------|------|----------------|---------|
| SAST | Semgrep | Code patterns, OWASP Top 10 | Push, PR, pre-push |
| SAST | Bandit | Python-specific security issues | Push, PR |
| SAST | CodeQL | Semantic code analysis | Push, PR, weekly |
| SAST | Ruff (`S` rules) | flake8-bandit security checks | Pre-commit, push, PR |
| Secrets | Betterleaks | BPE token secret detection (98.6% recall) | Pre-commit, pre-push, push, PR |
| Dependencies | uv audit | OSV database (native uv.lock) | Push, PR, pre-push |
| Dependencies | OSV-Scanner | OSV database (lockfile) | Push, PR, pre-push, daily |
| Dependencies | Trivy | Multi-source vuln DB | Push, PR, pre-push, daily |
| Dependencies | Grype | SBOM-based vulnerability scan | Push, PR, daily |
| Dependencies | pip-audit | PyPI Advisory DB | Local (`mise run security`) |
| Licenses | pip-licenses | Copyleft/problematic license detection | Push, PR |
| Licenses | Dependency Review | PR-time license + vuln gate | PR |
| Supply Chain | OpenSSF Scorecard | Repository security posture | Push to main, weekly |
| Supply Chain | Dependabot | Automated dependency updates | Weekly |
| SBOM | Syft | CycloneDX + SPDX generation | Push, PR |
