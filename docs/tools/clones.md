# Clone Detection

The `detect_clones` tool finds duplicate and near-duplicate code blocks across files using [jscpd](https://github.com/kucherenko/jscpd) (JS Copy/Paste Detector).

## Purpose

Clone detection helps identify:

- Copy-paste code that should be refactored into shared helpers
- Cross-file duplication that inflates maintenance burden
- Duplication percentage as a code health metric

Results can be ingested into the code graph as `SIMILAR_TO` edges via `code_graph_ingest_clones`.

## Usage

```python
detect_clones(
    repo_path="/path/to/repo",
    min_lines=5,
    min_tokens=50,
    include_globs="**/*.py,**/*.ts",
    threshold=0,
)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_path` | `str` | required | Repository root path |
| `min_lines` | `int` | 5 | Minimum clone block size in lines |
| `min_tokens` | `int` | 50 | Minimum clone block size in tokens |
| `include_globs` | `str` | `""` | Comma-separated glob patterns (e.g., `"**/*.py,**/*.ts"`) |
| `threshold` | `int` | 0 | Minimum duplication percentage to report (0--100, 0 = report all) |

## Output

The tool returns JSON with clone groups:

```json
{
  "status": "success",
  "total_clones": 3,
  "duplication_percentage": 4.52,
  "clones": [
    {
      "first_file": "src/tools/discovery.py",
      "first_start": 120,
      "first_end": 145,
      "second_file": "src/tools/git.py",
      "second_start": 80,
      "second_end": 105,
      "lines": 25,
      "tokens": 180,
      "fragment": "def run_command(cmd, cwd=None, timeout=120)..."
    }
  ]
}
```

Results are capped at 50 clones. Each clone's `fragment` field is truncated to 200 characters.

## Prerequisites

Requires `npx` to be available on the system. The tool runs `npx -y jscpd@4` with pinned version for reproducibility.

!!! tip
    Clone detection works best on repositories with at least 10 files. For very small projects, duplication is typically low and the overhead is not worthwhile.

## Input Validation

- `repo_path` is validated with `validate_repo_path` (path traversal prevention, must exist, must be a directory)
- `include_globs` patterns are validated with `validate_glob_pattern` (blocks command injection characters)
