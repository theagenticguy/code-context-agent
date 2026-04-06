# Installation

## Prerequisites

### Python Environment

- **Python 3.13+** (required)
- **uv** (Astral's fast package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### AWS Configuration

Requires AWS credentials configured for Amazon Bedrock access:

```bash
aws configure
# or set environment variables
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
```

Default model: `global.anthropic.claude-opus-4-6-v1` (configurable via `CODE_CONTEXT_MODEL_ID`)

### External CLI Tools

| Tool | Installation | Purpose |
|------|--------------|---------|
| **ripgrep** | `cargo install ripgrep` | File search and manifest creation |
| **gitnexus** | `npm install -g gitnexus` | Structural code intelligence (Tree-sitter parsing, clustering, execution flows) |
| **repomix** | `npm install -g repomix` | Code bundling with Tree-sitter compression |
| **npx** | Included with Node.js | Required for context7 library docs and knip dead code detection |

Optional static analysis tools (enrich indexer output):

| Tool | Installation | Purpose |
|------|--------------|---------|
| **semgrep** | `pip install semgrep` or `brew install semgrep` | Security findings and OWASP scanning |
| **ty** | `uv tool install ty` | Python type checker |
| **ruff** | `uv tool install ruff` | Python linter |
| **radon** | `pip install radon` | Cyclomatic complexity analysis |
| **vulture** | `pip install vulture` | Python dead code detection |

---

## Install

=== "uv tool (recommended)"

    ```bash
    uv tool install code-context-agent
    ```

    This installs the CLI globally and makes the `code-context-agent` command available.

=== "Development setup"

    ```bash
    git clone https://github.com/theagenticguy/code-context-agent.git
    cd code-context-agent
    uv sync --all-groups
    uv run code-context-agent
    ```

    This installs all dependency groups including dev tools (ruff, pytest, commitizen) and security tools (bandit, semgrep).

## Verify Installation

```bash
# Check version
code-context-agent --version

# Verify external tool dependencies
code-context-agent check

# Show help
code-context-agent --help
```

The `check` command verifies that core tools (ripgrep, gitnexus, repomix, npx), static analysis tools (semgrep, ruff, ty, radon, vulture, pipdeptree), security scanners (betterleaks, bandit, osv-scanner), and AWS credentials are available. See [Check Command](check-command.md) for details.
