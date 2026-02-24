# LSP Integration

The Language Server Protocol (LSP) integration provides semantic analysis capabilities across multiple programming languages.

## Supported Languages

| Language | Server | Installation |
|----------|--------|--------------|
| Python | ty | `uv tool install ty` |
| TypeScript/JavaScript | typescript-language-server | `npm install -g typescript-language-server` |
| Rust | rust-analyzer | `rustup component add rust-analyzer` |
| Go | gopls | `go install golang.org/x/tools/gopls@latest` |
| Java | jdtls | Eclipse JDT Language Server |

Server configuration is managed via the `CODE_CONTEXT_LSP_SERVERS` environment variable. See [Configuration](../getting-started/configuration.md#lsp-server-registry).

## LSP Fallback Chain

When the primary LSP server for a language fails to start, the agent attempts a fallback chain before giving up:

1. **Primary server** --- The configured server for the language
2. **Alternative server** --- A secondary option if available
3. **Graceful degradation** --- Reports the failure and compensates with AST and search tools

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
