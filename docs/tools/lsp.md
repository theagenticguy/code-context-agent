# LSP Integration

The Language Server Protocol (LSP) integration provides semantic analysis capabilities across multiple programming languages.

## Supported Languages

| Language | Server(s) | Installation |
|----------|-----------|--------------|
| Python | `ty server`, `pyright-langserver --stdio` | `uv tool install ty` |
| TypeScript/JavaScript | `typescript-language-server --stdio` | `npm install -g typescript-language-server` |
| Rust | `rust-analyzer` | `rustup component add rust-analyzer` |
| Go | `gopls serve` | `go install golang.org/x/tools/gopls@latest` |
| Java | `jdtls` | Eclipse JDT Language Server |

Server configuration is managed via the `CODE_CONTEXT_LSP_SERVERS` environment variable. See [Configuration](../getting-started/configuration.md#lsp-server-registry).

## LSP Fallback Chain

Each language maps to an **ordered list** of server commands. When the primary server fails to start, the agent automatically tries the next server in the chain:

```json
{
  "py": ["ty server", "pyright-langserver --stdio"],
  "ts": ["typescript-language-server --stdio"],
  "rust": ["rust-analyzer"],
  "go": ["gopls serve"],
  "java": ["jdtls"]
}
```

For Python, the chain is:

1. `ty server` (primary -- fast Rust-based type checker)
2. `pyright-langserver --stdio` (fallback -- Microsoft's Python LSP)
3. Graceful degradation -- reports the failure and compensates with AST and search tools

This fallback mechanism is implemented in `_try_fallback_session()` in `tools/lsp/tools.py`.

## Tools

### `lsp_start`

Initializes the LSP server for a detected language. Handles server startup, capability negotiation, and workspace initialization.

### `lsp_document_symbols`

Retrieves all symbols (functions, classes, variables, etc.) defined in a file. Provides a structural overview without reading the full source.

### `lsp_references`

Finds all references to a symbol across the workspace. Critical for understanding usage patterns and dependency relationships.

### `lsp_definition`

Navigates to the definition of a symbol. Used to trace call chains and understand implementation details.

### `lsp_hover`

Retrieves hover information (type signatures, documentation) for a symbol at a specific position.

### `lsp_workspace_symbols`

Searches for symbols across the entire workspace by name pattern. Useful for finding related implementations.

### `lsp_diagnostics`

Retrieves diagnostic information (errors, warnings) for a file. Surfaces type errors, unresolved references, and other issues.

### `lsp_shutdown`

Shuts down an LSP server session to free resources. Sessions are automatically cleaned up when the agent finishes, but explicit shutdown is more efficient during long analysis runs.
