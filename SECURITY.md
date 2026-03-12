# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 6.x     | Yes       |
| < 6.0   | No        |

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

- Dependencies are pinned via `uv.lock` and audited by OSV-Scanner, Trivy, and Bandit in CI
- GitHub Actions are pinned to commit SHAs to prevent supply chain attacks
- Gitleaks scans for leaked secrets on every push
