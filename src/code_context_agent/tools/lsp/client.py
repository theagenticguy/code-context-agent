"""LSP JSON-RPC client over stdio.

This module implements a Language Server Protocol client that communicates
with language servers using JSON-RPC 2.0 over stdio with Content-Length framing.

The LSP specification requires messages to be framed with HTTP-like headers:
    Content-Length: <length>\r\n
    \r\n
    <json body>

Reference: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LspClient:
    """LSP client using JSON-RPC 2.0 over stdio.

    This client manages communication with an LSP server subprocess,
    handling the Content-Length message framing and request/response
    correlation.

    Attributes:
        workspace_path: Path to the workspace root.
        server_cmd: Command to start the LSP server.

    Example:
        >>> client = LspClient()
        >>> await client.start(["typescript-language-server", "--stdio"], "/path/to/workspace")
        >>> symbols = await client.document_symbols("/path/to/file.ts")
        >>> await client.shutdown()
    """

    def __init__(self, request_timeout: float = 30.0) -> None:
        """Initialize the LSP client.

        Args:
            request_timeout: Timeout in seconds for LSP requests (default 30.0).
        """
        self._process: asyncio.subprocess.Process | None = None
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._initialized = False
        self.workspace_path: str = ""
        self.server_cmd: list[str] = []
        self.request_timeout: float = request_timeout

    async def start(
        self,
        server_cmd: list[str],
        workspace_path: str,
        startup_timeout: float = 30.0,
        initialization_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start LSP server and initialize the connection.

        Args:
            server_cmd: Command and arguments to start the LSP server.
            workspace_path: Absolute path to the workspace root.
            startup_timeout: Maximum seconds to wait for server initialization.
            initialization_options: Optional initialization options for the server.

        Returns:
            Server capabilities from the initialize response.

        Raises:
            RuntimeError: If server fails to start or initialize within timeout.
        """
        self.server_cmd = server_cmd
        self.workspace_path = workspace_path

        logger.info(f"Starting LSP server: {' '.join(server_cmd)} (timeout: {startup_timeout}s)")

        try:
            # Create subprocess with timeout
            try:
                self._process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *server_cmd,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=workspace_path,
                    ),
                    timeout=startup_timeout,
                )
            except TimeoutError as err:
                logger.error(f"LSP server failed to start within {startup_timeout}s")
                raise RuntimeError(f"LSP server failed to start within {startup_timeout}s") from err

            if self._process.stdout is None or self._process.stdin is None:
                raise RuntimeError("Failed to create subprocess pipes")

            # Start background reader
            self._reader_task = asyncio.create_task(self._read_responses())

            # Send initialize request per LSP spec with timeout
            root_uri = Path(workspace_path).as_uri()
            init_params: dict[str, Any] = {
                "processId": None,
                "rootUri": root_uri,
                "capabilities": {
                    "workspace": {"workspaceFolders": True},
                    "textDocument": {
                        "documentSymbol": {
                            "hierarchicalDocumentSymbolSupport": True,
                        },
                        "definition": {},
                        "references": {},
                        "hover": {
                            "contentFormat": ["markdown", "plaintext"],
                        },
                    },
                },
                "workspaceFolders": [{"uri": root_uri, "name": Path(workspace_path).name}],
                "clientInfo": {"name": "code-context-agent", "version": "0.1.0"},
            }

            # Add initialization options if provided (e.g., pyright config)
            if initialization_options:
                init_params["initializationOptions"] = initialization_options

            try:
                init_result = await asyncio.wait_for(
                    self._request("initialize", init_params),
                    timeout=startup_timeout,
                )
            except TimeoutError as err:
                logger.error(f"LSP initialization timed out after {startup_timeout}s")
                raise RuntimeError(f"LSP initialization timed out after {startup_timeout}s") from err

            if "error" in init_result:
                raise RuntimeError(f"LSP initialize error: {init_result['error']}")

            # Send initialized notification
            await self._notify("initialized", {})
            self._initialized = True

            logger.info("LSP server initialized successfully")
            return init_result.get("result", {})

        except Exception:
            # Clean up on any failure
            await self._cleanup_on_error()
            raise

    async def _cleanup_on_error(self) -> None:
        """Clean up resources after an error during startup."""
        logger.debug("Cleaning up LSP client after error")

        # Cancel reader task if running
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        # Terminate process if running
        if self._process is not None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                self._process.kill()
                try:
                    await self._process.wait()
                except Exception as e:
                    logger.debug(f"Process wait interrupted: {e}")
            except Exception as e:
                logger.warning(f"Error terminating LSP process: {e}")
            self._process = None

        # Clear pending requests
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

        self._initialized = False

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for response.

        Args:
            method: LSP method name (e.g., "textDocument/documentSymbol").
            params: Method parameters.

        Returns:
            The JSON-RPC response (with 'result' or 'error' key).

        Raises:
            TimeoutError: If response not received within timeout.
            RuntimeError: If client not connected.
        """
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("LSP client not connected")

        self._msg_id += 1
        msg_id = self._msg_id

        # Create future for response
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[msg_id] = future

        # Build and send request
        payload = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params,
        }
        await self._send(payload)

        # Wait for response with timeout
        try:
            return await asyncio.wait_for(future, timeout=self.request_timeout)
        except TimeoutError as err:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"LSP request timeout: {method}") from err

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected).

        Args:
            method: LSP method name.
            params: Method parameters.
        """
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("LSP client not connected")

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._send(payload)

    async def _send(self, payload: dict[str, Any]) -> None:
        """Send a JSON-RPC message with Content-Length framing.

        Args:
            payload: JSON-RPC message to send.
        """
        if self._process is None or self._process.stdin is None:
            return

        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")

        self._process.stdin.write(header + body)
        await self._process.stdin.drain()

    async def _read_responses(self) -> None:
        """Background task to read and dispatch responses."""
        if self._process is None or self._process.stdout is None:
            return

        buffer = b""

        while True:
            try:
                # Read available data
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    logger.debug("LSP server stdout closed")
                    break

                buffer += chunk

                # Parse complete messages from buffer
                while True:
                    # Look for header end
                    header_end = buffer.find(b"\r\n\r\n")
                    if header_end == -1:
                        break

                    # Parse Content-Length header
                    header = buffer[:header_end].decode("ascii", errors="replace")
                    content_length = None
                    for line in header.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            content_length = int(line.split(":")[1].strip())
                            break

                    if content_length is None:
                        logger.warning("LSP message missing Content-Length header")
                        buffer = buffer[header_end + 4 :]
                        continue

                    # Check if we have the full body
                    body_start = header_end + 4
                    body_end = body_start + content_length

                    if len(buffer) < body_end:
                        # Need more data
                        break

                    # Extract and parse body
                    body = buffer[body_start:body_end]
                    buffer = buffer[body_end:]

                    try:
                        message = json.loads(body.decode("utf-8"))
                        self._dispatch_message(message)
                    except json.JSONDecodeError as e:
                        logger.warning(f"LSP invalid JSON: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"LSP reader error: {e}")
                break

    def _dispatch_message(self, message: dict[str, Any]) -> None:
        """Dispatch a received JSON-RPC message.

        Args:
            message: Parsed JSON-RPC message.
        """
        # Response to our request
        if "id" in message and ("result" in message or "error" in message):
            msg_id = message["id"]
            if isinstance(msg_id, int) and msg_id in self._pending:
                future = self._pending.pop(msg_id)
                if not future.done():
                    future.set_result(message)
        # Server notification (e.g., diagnostics)
        elif "method" in message and "id" not in message:
            # Could handle notifications like publishDiagnostics here
            logger.debug(f"LSP notification: {message.get('method')}")

    async def did_open(self, file_path: str, language_id: str | None = None) -> None:
        """Notify server that a document was opened.

        Args:
            file_path: Absolute path to the file.
            language_id: Language identifier (auto-detected if not provided).

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if language_id is None:
            language_id = self._detect_language(path)

        text = path.read_text(encoding="utf-8", errors="replace")

        await self._notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": path.as_uri(),
                    "languageId": language_id,
                    "version": 1,
                    "text": text,
                },
            },
        )

    async def document_symbols(self, file_path: str) -> list[dict[str, Any]]:
        """Get document symbols (outline).

        Args:
            file_path: Absolute path to the file.

        Returns:
            List of DocumentSymbol or SymbolInformation objects.
        """
        path = Path(file_path)

        # Ensure document is open
        await self.did_open(file_path)

        response = await self._request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": path.as_uri()}},
        )

        return response.get("result", []) or []

    async def hover(self, file_path: str, line: int, character: int) -> dict[str, Any] | None:
        """Get hover information at position.

        Args:
            file_path: Absolute path to the file.
            line: 0-indexed line number.
            character: 0-indexed column number.

        Returns:
            Hover information with contents, or None if not available.
        """
        path = Path(file_path)

        response = await self._request(
            "textDocument/hover",
            {
                "textDocument": {"uri": path.as_uri()},
                "position": {"line": line, "character": character},
            },
        )

        return response.get("result")

    async def references(
        self, file_path: str, line: int, character: int, include_declaration: bool = True,
    ) -> list[dict[str, Any]]:
        """Find all references to symbol at position.

        Args:
            file_path: Absolute path to the file.
            line: 0-indexed line number.
            character: 0-indexed column number.
            include_declaration: Whether to include the declaration.

        Returns:
            List of Location objects with uri and range.
        """
        path = Path(file_path)

        response = await self._request(
            "textDocument/references",
            {
                "textDocument": {"uri": path.as_uri()},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": include_declaration},
            },
        )

        return response.get("result", []) or []

    async def definition(self, file_path: str, line: int, character: int) -> list[dict[str, Any]]:
        """Go to definition of symbol at position.

        Args:
            file_path: Absolute path to the file.
            line: 0-indexed line number.
            character: 0-indexed column number.

        Returns:
            List of Location objects.
        """
        path = Path(file_path)

        response = await self._request(
            "textDocument/definition",
            {
                "textDocument": {"uri": path.as_uri()},
                "position": {"line": line, "character": character},
            },
        )

        result = response.get("result")
        if result is None:
            return []
        if isinstance(result, dict):
            return [result]
        return result

    async def shutdown(self) -> None:
        """Shutdown the LSP server gracefully."""
        if self._process is None:
            return

        try:
            # Send shutdown request
            await self._request("shutdown", {})
            # Send exit notification
            await self._notify("exit", {})
        except Exception as e:
            logger.warning(f"LSP shutdown error: {e}")
        finally:
            # Cancel reader task
            if self._reader_task:
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass

            # Terminate process
            if self._process:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except TimeoutError:
                    self._process.kill()

            self._process = None
            self._initialized = False
            self._pending.clear()

    def _detect_language(self, path: Path) -> str:
        """Detect language ID from file extension.

        Args:
            path: File path.

        Returns:
            Language ID string.
        """
        extension_map = {
            ".ts": "typescript",
            ".tsx": "typescriptreact",
            ".js": "javascript",
            ".jsx": "javascriptreact",
            ".py": "python",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
        }
        return extension_map.get(path.suffix.lower(), "plaintext")

    @property
    def is_connected(self) -> bool:
        """Check if client is connected to server."""
        return self._process is not None and self._initialized
