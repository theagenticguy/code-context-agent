"""LSP (Language Server Protocol) tools package.

Provides tools for semantic code analysis via real LSP JSON-RPC over stdio.
"""

from .session import LspSessionManager
from .tools import (
    lsp_definition,
    lsp_document_symbols,
    lsp_hover,
    lsp_references,
    lsp_shutdown,
    lsp_start,
)

__all__ = [
    "LspSessionManager",
    "lsp_definition",
    "lsp_document_symbols",
    "lsp_hover",
    "lsp_references",
    "lsp_shutdown",
    "lsp_start",
]
