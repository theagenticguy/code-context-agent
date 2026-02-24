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

## LSP Server Registry

The `CODE_CONTEXT_LSP_SERVERS` variable accepts a JSON object mapping language keys to server commands:

```json
{
  "ts": "typescript-language-server --stdio",
  "py": "ty server",
  "rs": "rust-analyzer",
  "go": "gopls",
  "java": "jdtls"
}
```

The agent will attempt to start the appropriate LSP server based on the detected languages in the target codebase. If a server fails to start, the agent reports the failure and compensates with other signal sources (see [Tenet 6: Fail loud, fill gaps](../architecture/tenets.md#6-fail-loud-fill-gaps)).

## Configuration via pydantic-settings

Configuration is implemented using `pydantic-settings`, which provides:

- Environment variable parsing with the `CODE_CONTEXT_` prefix
- Type validation and coercion
- Default values
- JSON parsing for complex types (like `LSP_SERVERS`)

See the [`config` module](../reference/config.md) in the API reference for the full `Settings` model.
