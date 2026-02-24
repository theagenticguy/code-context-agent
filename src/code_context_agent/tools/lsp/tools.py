"""LSP tool wrappers for strands agent.

This module provides @tool decorated functions that wrap LSP client
operations for use by the strands agent. Each tool handles session
management and JSON serialization.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger
from strands import tool

from ...config import get_settings
from .client import LspClient
from .session import get_session_manager


async def _try_fallback_session(
    session_id: str, file_path: str,
) -> tuple[list, str] | None:
    """Try fallback LSP servers when the primary returned empty results.

    Parses the session_id to determine language kind and workspace, then
    tries each fallback server command (skipping the first, already tried).

    Args:
        session_id: Original session ID (format: "kind:workspace").
        file_path: Absolute path to the file for document_symbols.

    Returns:
        Tuple of (symbols, server_name) if a fallback produced results, or None.
    """
    parts = session_id.split(":", 1)
    if len(parts) != 2:
        return None

    kind, workspace = parts
    settings = get_settings()

    cmd_list = settings.lsp_servers.get(kind)
    if cmd_list is None or len(cmd_list) < 2:
        return None

    manager = get_session_manager()
    fallback_key = f"{kind}-fallback:{workspace}"

    # Check if we already have a fallback session running
    existing = manager.get_session(fallback_key)
    if existing is not None:
        try:
            symbols = await existing.document_symbols(str(Path(file_path).resolve()))
            server_name = manager.get_server_command_for_session(fallback_key) or "unknown"
            if symbols:
                return symbols, server_name
        except (OSError, TimeoutError, RuntimeError, ValueError) as e:
            logger.warning(f"Fallback session failed for document_symbols: {e}")
        return None

    # Try each fallback command (skip index 0 which was the primary)
    import shlex

    for i, cmd_str in enumerate(cmd_list[1:], start=1):
        cmd = shlex.split(cmd_str)
        try:
            client = LspClient(request_timeout=float(settings.lsp_timeout))
            init_options = manager._get_workspace_config(kind)
            await client.start(
                cmd,
                workspace,
                startup_timeout=float(settings.lsp_startup_timeout),
                initialization_options=init_options,
            )
            manager._sessions[fallback_key] = client
            manager._server_commands[fallback_key] = cmd_str

            symbols = await client.document_symbols(str(Path(file_path).resolve()))
            if symbols:
                logger.info(
                    f"LSP result-level fallback succeeded with: {cmd_str}",
                )
                return symbols, cmd_str

            # Server started but also returned empty; try next
            logger.debug(
                f"LSP fallback server '{cmd_str}' also returned empty symbols",
            )
        except (OSError, TimeoutError, RuntimeError, ValueError) as e:
            logger.warning(
                f"LSP fallback server '{cmd_str}' failed: {e}",
            )
            if i < len(cmd_list) - 1:
                continue

    return None


@tool
async def lsp_start(server_kind: str, workspace_path: str) -> str:
    """Start an LSP server and initialize workspace for semantic analysis.

    USE THIS TOOL:
    - Before using any other lsp_* tools (required prerequisite)
    - Once per language per workspace (session is reused automatically)
    - When you need semantic analysis: symbols, references, definitions, hover

    DO NOT USE:
    - If you already started an LSP session for this language/workspace combo
    - For simple text searches (use rg_search instead - much faster)
    - For repos without the target language (e.g., don't start "ts" for Python-only repo)

    Supported server kinds:
    - "ts": TypeScript/JavaScript (typescript-language-server)
    - "py": Python (ty server, with pyright-langserver fallback)

    Args:
        server_kind: Server type - "ts" for TypeScript/JS, "py" for Python.
        workspace_path: Absolute path to the repository/workspace root.

    Returns:
        Session ID (format: "kind:path") for use in subsequent LSP calls.

    Output Size: ~150 bytes JSON response.

    Resource Usage:
        - Memory: 100-500MB per server (depends on project size)
        - Startup time: 2-30 seconds (indexing dependent)
        - Sessions persist until lsp_shutdown or agent exit

    Common Errors:
        - "typescript-language-server not found": npm install -g typescript-language-server
        - "ty not found": uv tool install ty or pip install ty
        - Timeout: Large projects may exceed startup_timeout, increase in config
        - "No tsconfig.json": TypeScript server needs tsconfig.json in workspace

    Example success:
        {"status": "success", "session_id": "ts:/path/repo", "message": "LSP server started..."}

    Workflow:
        1. lsp_start("ts", "/repo")  # Start once
        2. lsp_document_symbols(session_id, file)  # Use many times
        3. lsp_references(session_id, file, line, char)
        4. lsp_shutdown(session_id)  # Optional cleanup
    """
    manager = get_session_manager()
    workspace = str(Path(workspace_path).resolve())
    settings = get_settings()

    try:
        await manager.get_or_create(server_kind, workspace, startup_timeout=settings.lsp_startup_timeout)
    except (OSError, TimeoutError, RuntimeError, ValueError) as e:
        logger.error(f"LSP server failed to start: {e}")
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
                "message": f"LSP server failed to start for {server_kind}. "
                "This is a CRITICAL FAILURE - do not proceed without LSP. "
                "Fix the issue and retry.",
            },
        )

    # Normalize kind for consistent session ID
    kind = server_kind.lower()
    aliases = {"typescript": "ts", "python": "py", "javascript": "ts"}
    kind = aliases.get(kind, kind)
    session_id = f"{kind}:{workspace}"

    server_cmd = manager.get_server_command_for_session(session_id) or server_kind

    return json.dumps(
        {
            "status": "success",
            "session_id": session_id,
            "server": server_cmd,
            "message": f"LSP server started for {server_kind} at {workspace}",
        },
    )


@tool
async def lsp_document_symbols(session_id: str, file_path: str) -> str:
    """Get document symbol outline (functions, classes, methods, variables).

    USE THIS TOOL:
    - To get a structural overview of a file without reading full contents
    - To find function/class names and their line ranges for targeted reading
    - To understand file organization before diving into implementation
    - To get accurate symbol positions for lsp_references or lsp_hover calls

    DO NOT USE:
    - Before calling lsp_start (will fail with "No active LSP session")
    - For searching across multiple files (use rg_search instead)
    - For simple line counting or file metadata (use read_file_bounded)

    Requires: Call lsp_start first to create a session.

    Args:
        session_id: Session ID from lsp_start (format: "kind:workspace").
        file_path: Absolute path to the file to analyze.

    Returns:
        JSON with symbols array containing name, kind, range, and nested children.

    Output Size: ~100-500 bytes per symbol. Typical file: 1-5KB response.

    Symbol Kinds (common values):
        - 5: Class
        - 6: Method
        - 12: Function
        - 13: Variable
        - 14: Constant
        - 23: Struct

    Common Errors:
        - "No active LSP session": Call lsp_start first
        - Empty symbols array: File may not be parseable or have no exports
        - "File not found": Ensure file_path is absolute and exists

    Example success:
        {"status": "success", "file": "/repo/src/index.ts", "symbols": [
            {"name": "main", "kind": 12, "range": {"start": {"line": 10}}, "children": []}
        ], "count": 5}

    Workflow tip:
        1. Use lsp_document_symbols to find symbol names and line numbers
        2. Use read_file_bounded with start_line to read specific sections
        3. Use lsp_references to find where symbols are used
    """
    manager = get_session_manager()
    client = manager.get_session(session_id)

    if client is None:
        return json.dumps(
            {
                "status": "error",
                "error": f"No active LSP session: {session_id}. Call lsp_start first.",
            },
        )

    server_cmd = manager.get_server_command_for_session(session_id) or "unknown"
    fallback_used = False

    try:
        symbols = await client.document_symbols(str(Path(file_path).resolve()))

        # Result-level fallback: if primary returned empty, try next server
        if not symbols:
            fallback = await _try_fallback_session(session_id, file_path)
            if fallback is not None:
                symbols, server_cmd = fallback
                fallback_used = True

        return json.dumps(
            {
                "status": "success",
                "file": file_path,
                "symbols": symbols,
                "count": len(symbols),
                "server": server_cmd,
                "fallback_used": fallback_used,
            },
        )
    except (OSError, TimeoutError, RuntimeError, ValueError) as e:
        logger.error(f"LSP document_symbols error: {e}")
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
            },
        )


@tool
async def lsp_hover(session_id: str, file_path: str, line: int, character: int) -> str:
    """Get hover information at a position (docstrings, JSDoc, type info).

    Retrieves documentation and type information for the symbol at the given
    position. This is how you extract docstrings and JSDoc comments.

    Requires: Call lsp_start first to create a session.

    Args:
        session_id: Session ID from lsp_start.
        file_path: Absolute path to the file.
        line: 0-indexed line number.
        character: 0-indexed column number.

    Returns:
        JSON object with hover contents (often includes markdown documentation).

    Example:
        >>> hover = await lsp_hover("ts:/path/repo", "/path/repo/src/utils.ts", 10, 5)
        >>> # Returns: {"contents": {"kind": "markdown", "value": "/**\n * Utility function..."}}
    """
    manager = get_session_manager()
    client = manager.get_session(session_id)

    if client is None:
        return json.dumps(
            {
                "status": "error",
                "error": f"No active LSP session: {session_id}. Call lsp_start first.",
            },
        )

    try:
        hover = await client.hover(str(Path(file_path).resolve()), line, character)
        return json.dumps(
            {
                "status": "success",
                "file": file_path,
                "position": {"line": line, "character": character},
                "hover": hover,
            },
        )
    except (OSError, TimeoutError, RuntimeError, ValueError) as e:
        logger.error(f"LSP hover error: {e}")
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
            },
        )


@tool
async def lsp_references(
    session_id: str,
    file_path: str,
    line: int,
    character: int,
    include_declaration: bool = True,
) -> str:
    """Find all references to symbol at position (fan-in analysis).

    Use this to understand how widely a symbol is used across the codebase.
    The number of unique referencing files indicates the symbol's centrality.

    Requires: Call lsp_start first to create a session.

    Args:
        session_id: Session ID from lsp_start.
        file_path: Absolute path to the file.
        line: 0-indexed line number.
        character: 0-indexed column number.
        include_declaration: Whether to include the declaration itself.

    Returns:
        JSON array of Location objects with uri and range.

    Example:
        >>> refs = await lsp_references("ts:/path/repo", "/path/repo/src/api.ts", 25, 10)
        >>> # Returns: [{"uri": "file:///path/repo/src/handler.ts", "range": {...}}, ...]
    """
    manager = get_session_manager()
    client = manager.get_session(session_id)

    if client is None:
        return json.dumps(
            {
                "status": "error",
                "error": f"No active LSP session: {session_id}. Call lsp_start first.",
            },
        )

    try:
        refs = await client.references(str(Path(file_path).resolve()), line, character, include_declaration)

        # Count unique files for fan-in metric
        unique_files = set()
        for ref in refs:
            uri = ref.get("uri", "")
            if uri:
                unique_files.add(uri)

        return json.dumps(
            {
                "status": "success",
                "file": file_path,
                "position": {"line": line, "character": character},
                "references": refs,
                "total_count": len(refs),
                "unique_files": len(unique_files),
            },
        )
    except (OSError, TimeoutError, RuntimeError, ValueError) as e:
        logger.error(f"LSP references error: {e}")
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
            },
        )


@tool
async def lsp_definition(session_id: str, file_path: str, line: int, character: int) -> str:
    """Go to definition of symbol at position.

    Use this to find where a symbol is defined, useful for tracing
    dependencies and understanding code structure.

    Requires: Call lsp_start first to create a session.

    Args:
        session_id: Session ID from lsp_start.
        file_path: Absolute path to the file.
        line: 0-indexed line number.
        character: 0-indexed column number.

    Returns:
        JSON array of Location objects pointing to definition(s).

    Example:
        >>> defn = await lsp_definition("ts:/path/repo", "/path/repo/src/index.ts", 5, 12)
        >>> # Returns: [{"uri": "file:///path/repo/src/utils.ts", "range": {...}}]
    """
    manager = get_session_manager()
    client = manager.get_session(session_id)

    if client is None:
        return json.dumps(
            {
                "status": "error",
                "error": f"No active LSP session: {session_id}. Call lsp_start first.",
            },
        )

    try:
        definitions = await client.definition(str(Path(file_path).resolve()), line, character)
        return json.dumps(
            {
                "status": "success",
                "file": file_path,
                "position": {"line": line, "character": character},
                "definitions": definitions,
                "count": len(definitions),
            },
        )
    except (OSError, TimeoutError, RuntimeError, ValueError) as e:
        logger.error(f"LSP definition error: {e}")
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
            },
        )


@tool
async def lsp_shutdown(session_id: str) -> str:
    """Shutdown an LSP server session.

    Use this when you're done with a workspace to free resources.
    Sessions are automatically cleaned up when the agent finishes,
    but explicit shutdown is more efficient.

    Args:
        session_id: Session ID from lsp_start.

    Returns:
        JSON object with shutdown status.

    Example:
        >>> await lsp_shutdown("ts:/path/repo")
        >>> # Returns: {"status": "success", "message": "Session shutdown"}
    """
    manager = get_session_manager()

    success = await manager.shutdown_session(session_id)

    if success:
        return json.dumps(
            {
                "status": "success",
                "message": f"LSP session shutdown: {session_id}",
            },
        )
    return json.dumps(
        {
            "status": "warning",
            "message": f"No active session found: {session_id}",
        },
    )


@tool
async def lsp_workspace_symbols(
    session_id: str,
    query: str,
    max_results: int = 50,
) -> str:
    """Search for symbols across the entire workspace.

    USE THIS TOOL:
    - To find a symbol by name when you don't know which file it's in
    - For broad searches like "all classes named *Service*"
    - After lsp_start when you need workspace-wide symbol search

    DO NOT USE:
    - For symbols in a specific file (use lsp_document_symbols instead)
    - Before calling lsp_start

    Requires: ty LSP server supports workspace/symbol. TypeScript LSP also supports it.

    Args:
        session_id: Session ID from lsp_start.
        query: Search query string (partial name matching).
        max_results: Maximum symbols to return (default 50).

    Returns:
        JSON with symbols array containing name, kind, location.
    """
    manager = get_session_manager()
    client = manager.get_session(session_id)

    if client is None:
        return json.dumps(
            {
                "status": "error",
                "error": f"No active LSP session: {session_id}. Call lsp_start first.",
            },
        )

    try:
        symbols = await client.workspace_symbols(query)
        # Truncate to max_results
        truncated = symbols[:max_results]
        return json.dumps(
            {
                "status": "success",
                "query": query,
                "symbols": truncated,
                "count": len(truncated),
                "total": len(symbols),
            },
        )
    except (OSError, TimeoutError, RuntimeError, ValueError) as e:
        logger.error(f"LSP workspace_symbols error: {e}")
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
            },
        )


@tool
async def lsp_diagnostics(session_id: str, file_path: str) -> str:
    """Get diagnostic messages (errors, warnings) for a file.

    USE THIS TOOL:
    - To find type errors, unresolved references, and other issues
    - To assess code quality of a specific file
    - To find potential bugs that static analysis catches

    DO NOT USE:
    - Before calling lsp_start (will fail with "No active LSP session")
    - For non-language files (e.g., JSON, YAML) unless LSP supports them

    Requires: Call lsp_start first. Works best with ty (Python) server.

    Args:
        session_id: Session ID from lsp_start.
        file_path: Absolute path to the file.

    Returns:
        JSON with diagnostics array containing severity, message, range.
    """
    manager = get_session_manager()
    client = manager.get_session(session_id)

    if client is None:
        return json.dumps(
            {
                "status": "error",
                "error": f"No active LSP session: {session_id}. Call lsp_start first.",
            },
        )

    try:
        file_uri = Path(file_path).resolve().as_uri()
        diagnostics = await client.diagnostics(file_uri)
        return json.dumps(
            {
                "status": "success",
                "file": file_path,
                "diagnostics": diagnostics,
                "count": len(diagnostics),
            },
        )
    except (OSError, TimeoutError, RuntimeError, ValueError) as e:
        logger.error(f"LSP diagnostics error: {e}")
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
            },
        )
