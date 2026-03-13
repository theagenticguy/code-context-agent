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
| **ast-grep** | `cargo install ast-grep` | Structural code search |
| **repomix** | `npm install -g repomix` | Code bundling with Tree-sitter compression |
| **typescript-language-server** | `npm install -g typescript-language-server` | TypeScript/JavaScript LSP |
| **ty** | `uv tool install ty` | Python type checker/LSP server |

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

The `check` command verifies that ripgrep, ast-grep, repomix, and npx are installed and accessible. See [Check Command](check-command.md) for details.
