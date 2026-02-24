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
    ├── test_git.py                # Git tool tests
    └── graph/
        ├── test_adapters.py       # Graph adapter tests
        ├── test_analysis.py       # Graph analysis tests
        └── test_model.py          # Graph model tests
```

## Configuration

Pytest is configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

- **`asyncio_mode = "auto"`** --- Automatically detects and runs async test functions
- **`asyncio_default_fixture_loop_scope = "function"`** --- Each test gets its own event loop

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

- `D` --- Docstrings not required in tests
- `S101` --- `assert` statements allowed
- `ARG` --- Unused arguments allowed (common in fixtures)
