"""LSP session manager using singleton pattern.

This module provides a session manager that maintains LSP client connections
across tool calls. Sessions are expensive to start (subprocess spawn +
initialization), so we reuse them.
"""

from __future__ import annotations

from typing import Any, ClassVar

from loguru import logger

from ...config import get_settings
from .client import LspClient


class LspSessionManager:
    """Singleton session manager for LSP connections.

    Maintains a pool of LSP client connections keyed by server kind and
    workspace path. This allows multiple tools to share the same LSP
    connection efficiently.

    Session keys are formatted as "{server_kind}:{workspace_path}".

    Example:
        >>> manager = LspSessionManager()
        >>> client = await manager.get_or_create("ts", "/path/to/project")
        >>> symbols = await client.document_symbols("/path/to/file.ts")
        >>> await manager.shutdown_all()
    """

    _instance: ClassVar[LspSessionManager | None] = None
    _sessions: dict[str, LspClient]
    _server_commands: dict[str, str]

    def __new__(cls) -> LspSessionManager:
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions = {}
            cls._instance._server_commands = {}
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        if cls._instance is not None:
            cls._instance._sessions = {}
            cls._instance._server_commands = {}
        cls._instance = None

    def _get_server_commands(self, server_kind: str) -> list[list[str]]:
        """Get ordered LSP server commands by kind from configuration.

        Args:
            server_kind: Server type identifier.

        Returns:
            Ordered list of commands (each a list of args) to try.

        Raises:
            ValueError: If server kind is not supported.
        """
        import shlex

        settings = get_settings()

        # Normalize kind
        kind = server_kind.lower()
        aliases = {"typescript": "ts", "python": "py", "javascript": "ts"}
        kind = aliases.get(kind, kind)

        cmd_list = settings.lsp_servers.get(kind)
        if cmd_list is None:
            supported = ", ".join(sorted(settings.lsp_servers.keys()))
            raise ValueError(
                f"Unsupported LSP server kind: {server_kind}. Configured: {supported}",
            )

        return [shlex.split(cmd_str) for cmd_str in cmd_list]

    def _make_session_key(self, server_kind: str, workspace_path: str) -> str:
        """Create a session key from server kind and workspace.

        Args:
            server_kind: Server type identifier.
            workspace_path: Workspace root path.

        Returns:
            Session key string.
        """
        # Normalize server kind using same aliases as _get_server_commands
        kind = server_kind.lower()
        aliases = {"typescript": "ts", "python": "py", "javascript": "ts"}
        kind = aliases.get(kind, kind)
        return f"{kind}:{workspace_path}"

    def _get_workspace_config(self, server_kind: str) -> dict[str, Any] | None:
        """Generate workspace configuration for LSP server initialization.

        Args:
            server_kind: Server type identifier ("ts", "py", etc.).

        Returns:
            Initialization options dict for the LSP server, or None if not applicable.
        """
        # Normalize kind
        kind = server_kind.lower()
        aliases = {"typescript": "ts", "python": "py", "javascript": "ts"}
        kind = aliases.get(kind, kind)

        if kind == "py":
            # ty uses configuration from ty.toml or pyproject.toml [tool.ty]
            # No initialization options needed
            return None
        if kind == "ts":
            # TypeScript language server configuration
            # Uses the VS Code-style settings format
            return {
                "typescript": {
                    "preferences": {
                        "excludeLibrarySymbolsInNavTo": True,
                    },
                },
                "javascript": {
                    "preferences": {
                        "excludeLibrarySymbolsInNavTo": True,
                    },
                },
            }

        # Unknown languages: no special config needed
        return None

    def get_server_command_for_session(self, session_id: str) -> str | None:
        """Get the server command string that was used for a session.

        Args:
            session_id: Session identifier (format: "kind:workspace").

        Returns:
            The command string that successfully started the server, or None.
        """
        return self._server_commands.get(session_id)

    async def get_or_create(
        self,
        server_kind: str,
        workspace_path: str,
        startup_timeout: float | None = None,
    ) -> LspClient:
        """Get existing session or create new one with fallback chain.

        Tries each configured LSP server command in order. If one fails,
        falls back to the next. Stores which command succeeded for later
        inspection.

        Args:
            server_kind: Server type ("ts", "py", etc.).
            workspace_path: Absolute path to workspace root.
            startup_timeout: Maximum seconds to wait for server initialization.
                If None, uses the value from settings.

        Returns:
            Connected LspClient instance.

        Raises:
            RuntimeError: If all server commands fail to start.
            ValueError: If server kind is not supported.
        """
        if startup_timeout is None:
            startup_timeout = get_settings().lsp_startup_timeout

        key = self._make_session_key(server_kind, workspace_path)

        if key in self._sessions:
            client = self._sessions[key]
            if client.is_connected:
                logger.debug(f"Reusing LSP session: {key}")
                return client
            # Client disconnected, remove and recreate
            logger.debug(f"Removing disconnected LSP session: {key}")
            del self._sessions[key]
            self._server_commands.pop(key, None)

        logger.info(f"Creating new LSP session: {key}")
        settings = get_settings()

        # Normalize kind for workspace config lookup
        kind = server_kind.lower()
        aliases = {"typescript": "ts", "python": "py", "javascript": "ts"}
        kind = aliases.get(kind, kind)

        commands = self._get_server_commands(server_kind)
        last_error: OSError | TimeoutError | RuntimeError | None = None

        for i, cmd in enumerate(commands):
            try:
                client = LspClient(request_timeout=float(settings.lsp_timeout))
                init_options = self._get_workspace_config(kind)
                await client.start(
                    cmd,
                    workspace_path,
                    startup_timeout=startup_timeout,
                    initialization_options=init_options,
                )
                self._sessions[key] = client
                self._server_commands[key] = " ".join(cmd)
                if i > 0:
                    logger.info(f"LSP fallback succeeded with: {' '.join(cmd)}")
                return client
            except (OSError, TimeoutError, RuntimeError) as e:
                last_error = e
                if i < len(commands) - 1:
                    logger.warning(
                        f"LSP server '{' '.join(cmd)}' failed: {e}. Trying next fallback...",
                    )
                continue

        raise RuntimeError(
            f"All LSP servers failed for {server_kind}. Last error: {last_error}",
        )

    def get_session(self, session_id: str) -> LspClient | None:
        """Get an existing session by ID.

        Args:
            session_id: Session identifier (format: "kind:workspace").

        Returns:
            LspClient if session exists and is connected, None otherwise.
        """
        client = self._sessions.get(session_id)
        if client and client.is_connected:
            return client
        return None

    def list_sessions(self) -> list[str]:
        """List all active session IDs.

        Returns:
            List of session key strings.
        """
        return [key for key, client in self._sessions.items() if client.is_connected]

    async def shutdown_session(self, session_id: str) -> bool:
        """Shutdown a specific session.

        Args:
            session_id: Session identifier to shutdown.

        Returns:
            True if session was found and shutdown, False otherwise.
        """
        client = self._sessions.pop(session_id, None)
        self._server_commands.pop(session_id, None)
        if client:
            await client.shutdown()
            logger.info(f"Shutdown LSP session: {session_id}")
            return True
        return False

    async def shutdown_all(self) -> None:
        """Shutdown all active LSP sessions."""
        logger.info(f"Shutting down {len(self._sessions)} LSP sessions")
        for key, client in list(self._sessions.items()):
            try:
                await client.shutdown()
                logger.debug(f"Shutdown LSP session: {key}")
            except (OSError, TimeoutError, RuntimeError) as e:
                logger.warning(f"Error shutting down LSP session {key}: {e}")
        self._sessions.clear()
        self._server_commands.clear()


# Module-level singleton accessor
def get_session_manager() -> LspSessionManager:
    """Get the LSP session manager singleton.

    Returns:
        The global LspSessionManager instance.
    """
    return LspSessionManager()
