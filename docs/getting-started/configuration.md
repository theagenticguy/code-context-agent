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

## LSP Server Registry

The `CODE_CONTEXT_LSP_SERVERS` variable accepts a JSON object mapping language keys to **ordered lists** of server commands. Each list is a fallback chain -- if the first server fails, the next is tried automatically.

```json
{
  "py": ["ty server", "pyright-langserver --stdio"],
  "ts": ["typescript-language-server --stdio"],
  "rust": ["rust-analyzer"],
  "go": ["gopls serve"],
  "java": ["jdtls"]
}
```

For example, Python analysis first attempts `ty server`. If that fails to start (e.g., not installed), it falls back to `pyright-langserver --stdio`. If all servers in the chain fail, the agent compensates with other signal sources (see [Tenet 6: Fail loud, fill gaps](../architecture/tenets.md#6-fail-loud-fill-gaps)).

!!! tip
    To add a new language, extend the JSON with its key and an ordered list of server commands. The language key is matched against file extensions detected during analysis.

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
