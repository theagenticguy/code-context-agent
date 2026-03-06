# Testing

## Running Tests

```bash
# Run all tests
uv run pytest

# Verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_hooks.py

# Run tests matching pattern
uv run pytest -k "test_settings"

# Run in parallel (uses pytest-xdist)
uv run pytest -n auto

# With coverage
uv run pytest --cov=src/code_context_agent
```

## Test Structure

```
tests/
├── test_hooks.py                  # HookProvider tests
├── test_prompts.py                # Prompt rendering tests
├── models/
│   └── test_output.py             # Output model tests
└── tools/
    ├── test_discovery.py          # Discovery tool tests (rg_search count_only)
    ├── test_git.py                # Git tool tests
    ├── test_shell_security.py     # Shell security enforcement tests
    └── graph/
        ├── test_adapters.py       # Graph adapter tests
        ├── test_analysis.py       # Graph analysis tests
        └── test_model.py          # Graph model tests
```

The test suite covers models, tools, graph analysis, prompt rendering, and security enforcement. Run `uv run pytest` to see the current count.

## Configuration

Pytest is configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

- **`asyncio_mode = "auto"`** -- Automatically detects and runs async test functions
- **`asyncio_default_fixture_loop_scope = "function"`** -- Each test gets its own event loop

## Writing Tests

### Async Tests

Async tests run automatically thanks to `asyncio_mode = "auto"`:

```python
async def test_async_operation():
    result = await some_async_function()
    assert result is not None
```

### Per-file Ignores

Test files have relaxed linting rules (configured in `pyproject.toml`):

- `D` -- Docstrings not required in tests
- `S101` -- `assert` statements allowed
- `ARG` -- Unused arguments allowed (common in fixtures)

## Shell Security Tests

The `test_shell_security.py` file validates the shell tool's security enforcement:

```python
# Verifies allowed commands pass validation
def test_allows_safe_commands(self, cmd):
    assert _validate_command(cmd) is None

# Verifies shell operators are blocked
def test_blocks_shell_operators(self, cmd):
    result = _validate_command(cmd)
    assert result is not None
    assert "Blocked" in result

# Verifies git write operations are blocked
def test_blocks_git_write_ops(self, cmd):
    result = _validate_command(cmd)
    assert result is not None
    assert "read-only" in result
```

Tests cover allowed programs, blocked programs, shell operator blocking, git read-only enforcement, sensitive path prevention, and full integration through the `shell` tool function.
