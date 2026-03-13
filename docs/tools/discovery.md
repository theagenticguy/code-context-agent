# Discovery & Search Tools

## Discovery Tools

### `create_file_manifest`

Creates a complete inventory of the repository using ripgrep. This is typically the first tool called during analysis.

- Produces `files.all.txt` with all tracked files
- Respects `.gitignore` patterns
- Provides file counts by extension for language detection

### `repomix_orientation`

Generates a token distribution tree showing project structure with token counts per directory and file. Helps the agent understand the codebase's shape before diving into specific areas.

### `repomix_bundle`

Bundles selected files into a single markdown document using repomix with Tree-sitter compression. The output preserves file boundaries and includes metadata.

### `repomix_bundle_with_context`

Bundles repository files with git context (diffs and commit logs) in a single call. Unlike `repomix_bundle` which reads from a file list, this tool operates directly on a repo path with optional glob patterns.

- Always includes git context (working tree diffs and/or recent commit history)
- Supports `include_patterns` for scoping (e.g., `"src/**/*.py,tests/**/*.py"`)
- Configurable `include_logs_count` for number of recent commits
- Optional Tree-sitter compression and base64 truncation

### `repomix_compressed_signatures`

Extracts signatures and type information only, stripping function bodies via Tree-sitter. This provides the API surface of a codebase at a fraction of the token cost ([Tenet 3](../architecture/tenets.md#3-compress-aggressively-expand-selectively)).

### `repomix_split_bundle`

Splits large bundles into multiple chunks that fit within token budgets. Used for monorepos or large codebases that exceed single-bundle limits.

### `repomix_json_export`

Exports bundle data as structured JSON for programmatic consumption by downstream tools.

### `write_file_list`

Writes a list of file paths to a file for subsequent `repomix_bundle` calls. Used to create the curated file list (e.g., `files.business.txt`) before bundling.

- Deduplicates and sorts paths
- Creates parent directories automatically
- Returns the output path and file count

---

## Search Tools

### `rg_search`

Text search using ripgrep with support for regex patterns, file type filtering, glob filtering, and context lines. Supports a `count_only` mode that returns per-file match counts without the actual content.

Used for finding specific patterns, imports, configuration values, and string literals across the codebase.

### `read_file_bounded`

Reads a specific file with line range bounds. Used sparingly -- only for files that have earned deep reading through high scores across multiple signals.

### `write_file`

Writes content to a file within the `.code-context/` output directory. Used by the agent to persist `CONTEXT.md`, `FILE_INDEX.md`, and other analysis artifacts.

- Path must be within a `.code-context/` directory (security enforced)
- Creates parent directories automatically
- Returns the written path and byte count
