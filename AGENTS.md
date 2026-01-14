# Developer Tools Guide

This document describes the developer tools configured for this project and how to use them effectively.

## Prerequisites

All tools are managed via [uv](https://docs.astral.sh/uv/) and installed in the dev dependency group:

```bash
uv sync --all-groups
```

---

## Ruff (Linting & Formatting)

**Version**: `>=0.14.11`
**Documentation**: https://docs.astral.sh/ruff/

Ruff is an extremely fast Python linter and formatter written in Rust. It replaces flake8, isort, pyupgrade, and black.

### Configuration

Located in `pyproject.toml` under `[tool.ruff]`:

- **Line length**: 120 characters
- **Target**: Python 3.13
- **Docstring style**: Google convention

### Enabled Rule Categories

| Code | Category | Description |
|------|----------|-------------|
| E | pycodestyle errors | PEP 8 style errors |
| W | pycodestyle warnings | PEP 8 style warnings |
| F | Pyflakes | Logical errors (undefined names, unused imports) |
| I | isort | Import sorting |
| B | flake8-bugbear | Common bugs and design problems |
| C4 | flake8-comprehensions | Simplify comprehensions |
| UP | pyupgrade | Upgrade syntax to newer Python |
| ARG | flake8-unused-arguments | Unused function arguments |
| SIM | flake8-simplify | Simplify code |
| TCH | flake8-type-checking | Type checking imports optimization |
| PTH | flake8-use-pathlib | Prefer pathlib over os.path |
| ERA | eradicate | Remove commented-out code |
| PL | pylint | Pylint rules |
| RUF | Ruff-specific | Ruff's own rules |
| D | pydocstyle | Docstring conventions |
| S | flake8-bandit | Security checks |

### Commands

```bash
# Check for linting errors
uv run ruff check src/

# Check and auto-fix
uv run ruff check src/ --fix

# Check formatting
uv run ruff format --check src/

# Apply formatting
uv run ruff format src/

# Check everything (lint + format)
uv run ruff check src/ && uv run ruff format --check src/
```

### Per-file Ignores

- `tests/**/*.py`: Docstrings (D), assert statements (S101), unused args (ARG)
- `__init__.py`: Unused imports (F401)

---

## Ty (Type Checking)

**Version**: `>=0.0.11`
**Documentation**: https://docs.astral.sh/ty/

Ty is Astral's extremely fast Python type checker written in Rust. It's a modern alternative to mypy and pyright.

### Configuration

Located in `pyproject.toml` under `[tool.ty]`:

```toml
[tool.ty.rules]
possibly-unresolved-reference = "error"
invalid-argument-type = "error"
missing-argument = "error"
unsupported-operator = "error"
division-by-zero = "error"
unused-ignore-comment = "warn"
redundant-cast = "warn"

[tool.ty.environment]
python-version = "3.13"

[tool.ty.src]
include = ["src"]
```

### Rule Severity Levels

- **error**: Fails the check, blocks CI
- **warn**: Shows warning but doesn't fail
- **ignore**: Rule is disabled

### Commands

```bash
# Type check src/ directory
uv run ty check src/

# Type check specific file
uv run ty check src/code_context_agent/cli.py

# Check with verbose output
uv run ty check src/ --verbose
```

### Typing Guidelines

This project uses Python 3.13+ typing conventions:

```python
# DO: Use built-in generics
def process(items: list[str]) -> dict[str, int]: ...

# DON'T: Use typing module generics
from typing import List, Dict  # Deprecated
def process(items: List[str]) -> Dict[str, int]: ...

# DO: Use X | None for optional
def get_user(id: int) -> User | None: ...

# DON'T: Use Optional
from typing import Optional  # Deprecated
def get_user(id: int) -> Optional[User]: ...

# DO: Use X | Y for unions
def parse(value: str | int) -> Result: ...

# DON'T: Use Union
from typing import Union  # Deprecated
def parse(value: Union[str, int]) -> Result: ...
```

---

## Commitizen (Conventional Commits)

**Version**: `>=4.11.3`
**Documentation**: https://commitizen-tools.github.io/commitizen/

Commitizen enforces [Conventional Commits](https://www.conventionalcommits.org/) format and automates version bumping and changelog generation.

### Configuration

Located in `pyproject.toml` under `[tool.commitizen]`:

```toml
[tool.commitizen]
name = "cz_conventional_commits"
version = "0.1.0"
version_files = [
    "pyproject.toml:project.version",
    "src/code_context_agent/__init__.py:__version__"
]
tag_format = "v$version"
update_changelog_on_bump = true
version_scheme = "semver"
```

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature (bumps MINOR)
- `fix`: Bug fix (bumps PATCH)
- `docs`: Documentation only
- `style`: Formatting, no code change
- `refactor`: Code change that neither fixes nor adds
- `perf`: Performance improvement
- `test`: Adding tests
- `chore`: Maintenance tasks
- `ci`: CI/CD changes

**Breaking Changes**: Add `!` after type or `BREAKING CHANGE:` in footer (bumps MAJOR)

### Commands

```bash
# Interactive commit
uv run cz commit
# or
uv run cz c

# Bump version (auto-detects from commits)
uv run cz bump

# Bump specific version type
uv run cz bump --increment PATCH
uv run cz bump --increment MINOR
uv run cz bump --increment MAJOR

# Dry run (see what would happen)
uv run cz bump --dry-run

# Generate changelog only
uv run cz changelog

# Check if commits follow convention
uv run cz check --rev-range HEAD~5..HEAD
```

### Version Files

Commitizen automatically updates version in:
1. `pyproject.toml` → `project.version`
2. `src/code_context_agent/__init__.py` → `__version__`

---

## Pytest (Testing)

**Version**: `>=9.0.2`
**Documentation**: https://docs.pytest.org/

### Configuration

Located in `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

### Commands

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_cli.py

# Run tests matching pattern
uv run pytest -k "test_settings"

# Run with coverage
uv run pytest --cov=src/code_context_agent

# Run in parallel (requires pytest-xdist)
uv run pytest -n auto
```

---

## Security Tools

### Bandit

**Version**: `>=1.9.2`
Static security analyzer for Python.

```bash
# Scan source code
uv run bandit -r src/

# Scan with specific severity
uv run bandit -r src/ -ll  # Low and above
```

### pip-audit

**Version**: `>=2.10.0`
Audits dependencies for known vulnerabilities.

```bash
# Audit all dependencies
uv run pip-audit

# Output as JSON
uv run pip-audit --format=json
```

---

## CI/CD Integration

### Pre-commit Checks

Run all checks before committing:

```bash
# Full validation
uv run ruff check src/ && \
uv run ruff format --check src/ && \
uv run ty check src/ && \
uv run pytest
```

### Recommended Git Hooks

Create `.git/hooks/pre-commit`:

```bash
#!/bin/sh
uv run ruff check src/ --fix
uv run ruff format src/
uv run ty check src/
```

### GitHub Actions Example

```yaml
name: CI
on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --all-groups
      - run: uv run ruff check src/
      - run: uv run ruff format --check src/
      - run: uv run ty check src/
      - run: uv run pytest
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Install deps | `uv sync --all-groups` |
| Lint | `uv run ruff check src/` |
| Format | `uv run ruff format src/` |
| Type check | `uv run ty check src/` |
| Test | `uv run pytest` |
| Commit | `uv run cz commit` |
| Bump version | `uv run cz bump` |
| Security scan | `uv run bandit -r src/` |
| Audit deps | `uv run pip-audit` |
| Run CLI | `uv run code-context-agent` |
