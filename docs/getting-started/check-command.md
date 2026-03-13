# Check Command

*Added in v7.0.0*

The `check` command verifies that all external tool dependencies are installed and accessible. Run it before your first analysis to diagnose missing tools.

## Usage

```bash
code-context-agent check
```

## Output

Shows a checklist of required tools:

```
  ✓ ripgrep
  ✓ ast-grep
  ✓ repomix
  ✓ npx

All tools available.
```

Or if tools are missing:

```
  ✓ ripgrep
  ✗ ast-grep — install via ast-grep (npm)
  ✓ repomix
  ✗ npx — install via Node.js

Some tools are missing. Analysis may be limited.
```

Exit code: `0` if all tools are available, `1` if any are missing.

## Checked Tools

| Tool | Binary | Install Command | Purpose |
|------|--------|-----------------|---------|
| ripgrep | `rg` | `cargo install ripgrep` | File search and manifest creation |
| ast-grep | `ast-grep` | `npm install -g @ast-grep/cli` | Structural pattern matching |
| repomix | `repomix` | `npm install -g repomix` | Code bundling with Tree-sitter |
| npx | `npx` | Install Node.js | Required for context7 MCP server |

## Auto-Preflight in Full Mode

When running `--full` mode, the check is run automatically before analysis starts. If tools are missing, a warning is printed but analysis proceeds.

!!! tip
    Run `code-context-agent check` after installation to verify your environment before your first analysis.
