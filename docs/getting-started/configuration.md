# Configuration

All configuration uses environment variables with the `CODE_CONTEXT_` prefix.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CODE_CONTEXT_MODEL_ID` | `global.anthropic.claude-opus-4-6-v1` | Bedrock model ID |
| `CODE_CONTEXT_REGION` | `us-east-1` | AWS region |
| `CODE_CONTEXT_TEMPERATURE` | `1.0` | Model temperature (must be 1.0 for thinking) |
| `CODE_CONTEXT_LSP_SERVERS` | See below | LSP server registry (JSON) |
| `CODE_CONTEXT_AGENT_MAX_TURNS` | `1000` | Max agent turns |
| `CODE_CONTEXT_AGENT_MAX_DURATION` | `1200` | Timeout in seconds (default: 20 min) |
| `CODE_CONTEXT_CONTEXT7_ENABLED` | `true` | Enable context7 MCP server for library documentation lookup |
| `CODE_CONTEXT_OTEL_DISABLED` | `true` | Disable OpenTelemetry tracing (avoids context detachment errors) |
| `CODE_CONTEXT_FULL_MAX_DURATION` | `3600` | Max duration for `--full` mode in seconds (300-14400) |
| `CODE_CONTEXT_FULL_MAX_TURNS` | `3000` | Max agent turns for `--full` mode (100-10000) |
| `CODE_CONTEXT_APP_NAME` | `code-context-agent` | Application name for identification and logging |
| `CODE_CONTEXT_DEBUG` | `false` | Enable debug mode for verbose output and additional diagnostics |
| `CODE_CONTEXT_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `CODE_CONTEXT_OUTPUT_FORMAT` | `rich` | Output format: `rich` (TUI), `json`, or `plain` |

!!! note
    The `plain` format applies only to the root command output. The `analyze` subcommand accepts `rich` or `json` only.

| `CODE_CONTEXT_REASONING_EFFORT` | `high` | Reasoning effort level for standard mode |
| `CODE_CONTEXT_FULL_REASONING_EFFORT` | `max` | Reasoning effort level for `--full` mode (Opus 4.6 only) |

## Configuration via pydantic-settings

Configuration is implemented using `pydantic-settings`, which provides:

- Environment variable parsing with the `CODE_CONTEXT_` prefix
- Type validation and coercion
- Default values
- JSON parsing for complex types (like `LSP_SERVERS`)

See the [`config` module](../reference/config.md) in the API reference for the full `Settings` model.

## context7 Integration

When `CODE_CONTEXT_CONTEXT7_ENABLED` is `true` (the default), the analysis agent gains access to the [context7](https://context7.com) MCP server for looking up library documentation during analysis. This requires `npx` to be available on the system.

The context7 tools are prefixed with `context7_` in the agent's tool namespace:

- `context7_resolve-library-id` -- resolve a library name to a context7 ID
- `context7_query-docs` -- query documentation for a resolved library

To disable: `export CODE_CONTEXT_CONTEXT7_ENABLED=false`

## Full Mode Configuration

When `--full` is passed to the `analyze` command, the agent overrides several settings for exhaustive analysis:

| Setting | Standard Default | Full Mode Override |
|---------|-----------------|-------------------|
| `agent_max_duration` | 1200 (20 min) | `full_max_duration` (default: 3600 / 60 min) |
| `agent_max_turns` | 1000 | `full_max_turns` (default: 3000) |
| `lsp_max_files` | 5000 | 50,000 |

These overrides are applied via `Settings.model_copy()` at runtime. The original settings are not modified.

See [Full Mode](full-mode.md) for complete details on exhaustive analysis.

## Code Intelligence Configuration

Structural code intelligence is provided by GitNexus, which builds a Tree-sitter-powered knowledge graph. It is enabled by default and requires `npx` to be available.

```bash
# Disable GitNexus (not recommended)
export CODE_CONTEXT_GITNEXUS_ENABLED=false

# Disable context7 library documentation lookup
export CODE_CONTEXT_CONTEXT7_ENABLED=false
```

See [Architecture Overview](../architecture/overview.md) for implementation details.
