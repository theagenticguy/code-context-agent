# Developer Guide

## Setup

```bash
git clone <repository-url>
cd code-context-agent
uv sync --all-groups
```

## Common Tasks

| Task | Command |
|------|---------|
| Install dependencies | `uv sync --all-groups` |
| Run CLI | `uv run code-context-agent` |
| Lint | `uvx ruff check src/` |
| Format | `uvx ruff format src/` |
| Type check | `uvx ty check src/` |
| Test | `uv run pytest` |
| Commit (conventional) | `uv run cz commit` |
| Bump version | `uv run cz bump` |
| Security scan | `uv run bandit -r src/` |
| Audit deps | `uv run pip-audit` |

## Dependency Groups

| Group | Purpose | Install |
|-------|---------|---------|
| (default) | Runtime dependencies | `uv sync` |
| `dev` | Dev tools (ruff, pytest, commitizen) | `uv sync --group dev` |
| `security` | Security tools (bandit, pip-audit) | `uv sync --group security` |
| `docs` | Documentation (mkdocs-material) | `uv sync --group docs` |
| All groups | Everything | `uv sync --all-groups` |

## Versioning

This project uses [Commitizen](https://commitizen-tools.github.io/commitizen/) with [Conventional Commits](https://www.conventionalcommits.org/) for automated version management.

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:

| Type | Description | Version Bump |
|------|-------------|-------------|
| `feat` | New feature | MINOR |
| `fix` | Bug fix | PATCH |
| `docs` | Documentation only | None |
| `style` | Formatting, no code change | None |
| `refactor` | Code change that neither fixes nor adds | None |
| `perf` | Performance improvement | None |
| `test` | Adding tests | None |
| `chore` | Maintenance tasks | None |
| `ci` | CI/CD changes | None |

**Breaking changes**: Add `!` after type or `BREAKING CHANGE:` in footer (bumps MAJOR).

### Version Files

Commitizen updates version in two locations:

1. `pyproject.toml` -> `project.version`
2. `src/code_context_agent/__init__.py` -> `__version__`

## Pre-commit Checks

Run all checks before committing:

```bash
uvx ruff check src/ && \
uvx ruff format --check src/ && \
uvx ty check src/ && \
uv run pytest
```
