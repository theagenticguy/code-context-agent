# Code Style

## Ruff (Linting & Formatting)

[Ruff](https://docs.astral.sh/ruff/) handles both linting and formatting. It replaces flake8, isort, pyupgrade, and black.

### Configuration

- **Line length**: 120 characters
- **Target**: Python 3.13
- **Docstring style**: Google convention
- **Quote style**: Double quotes
- **Indent style**: Spaces

### Enabled Rule Categories

| Code | Category | Description |
|------|----------|-------------|
| `E` | pycodestyle errors | PEP 8 style errors |
| `W` | pycodestyle warnings | PEP 8 style warnings |
| `F` | Pyflakes | Logical errors (undefined names, unused imports) |
| `I` | isort | Import sorting |
| `B` | flake8-bugbear | Common bugs and design problems |
| `C4` | flake8-comprehensions | Simplify comprehensions |
| `C90` | mccabe | Cyclomatic complexity (max 10) |
| `BLE` | flake8-blind-except | Catch specific exceptions |
| `COM` | flake8-commas | Enforce trailing commas |
| `UP` | pyupgrade | Upgrade syntax to newer Python |
| `ARG` | flake8-unused-arguments | Unused function arguments |
| `SIM` | flake8-simplify | Simplify code |
| `TCH` | flake8-type-checking | Type checking imports optimization |
| `PTH` | flake8-use-pathlib | Prefer pathlib over os.path |
| `ERA` | eradicate | Remove commented-out code |
| `PL` | pylint | Pylint rules |
| `RUF` | Ruff-specific | Ruff's own rules |
| `D` | pydocstyle | Docstring conventions |
| `S` | flake8-bandit | Security checks |

### Commands

```bash
# Check for linting errors
uvx ruff check src/

# Check and auto-fix
uvx ruff check src/ --fix

# Check formatting
uvx ruff format --check src/

# Apply formatting
uvx ruff format src/
```

---

## Ty (Type Checking)

[Ty](https://docs.astral.sh/ty/) is Astral's Python type checker written in Rust.

### Rules

| Rule | Severity |
|------|----------|
| `possibly-unresolved-reference` | error |
| `invalid-argument-type` | error |
| `missing-argument` | error |
| `unsupported-operator` | error |
| `division-by-zero` | error |
| `unused-ignore-comment` | warn |
| `redundant-cast` | warn |

### Commands

```bash
# Type check src/ directory
uvx ty check src/

# Type check specific file
uvx ty check src/code_context_agent/cli.py
```

---

## Typing Conventions

This project uses Python 3.13+ typing conventions:

```python
# Use built-in generics
def process(items: list[str]) -> dict[str, int]: ...

# Use X | None for optional
def get_user(id: int) -> User | None: ...

# Use X | Y for unions
def parse(value: str | int) -> Result: ...
```

Avoid deprecated `typing` module generics (`List`, `Dict`, `Optional`, `Union`).

---

## Security Tools

### Bandit

Static security analyzer for Python:

```bash
uv run bandit -r src/
```

### OSV-Scanner

Dependency vulnerability scanner (replaces pip-audit):

```bash
# Run via CI (osv-scanner-action) or locally:
osv-scanner --lockfile uv.lock
```

### Security CI

The full security pipeline (CodeQL, Semgrep, Bandit, Gitleaks, OSV-Scanner, Trivy, Dependency Review, OpenSSF Scorecard) runs automatically in GitHub Actions on every push and PR. See [Security](../security/overview.md) for details.
