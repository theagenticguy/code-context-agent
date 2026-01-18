"""Custom tools package for code context analysis.

This package provides all tools used by the code context agent:
- Discovery: File manifests, repomix bundles, ripgrep search
- LSP: Language server operations for semantic analysis
- ast-grep: Structural code search with rule packs
- Shell: Bounded command execution
"""

from .astgrep import astgrep_inline_rule, astgrep_scan, astgrep_scan_rule_pack
from .discovery import (
    create_file_manifest,
    read_file_bounded,
    repomix_bundle,
    repomix_orientation,
    rg_search,
    write_file_list,
)
from .lsp import (
    lsp_definition,
    lsp_document_symbols,
    lsp_hover,
    lsp_references,
    lsp_shutdown,
    lsp_start,
)
from .shell import CommandResult, ToolResult, run_command
from .validation import (
    ValidationError,
    validate_file_path,
    validate_glob_pattern,
    validate_repo_path,
    validate_search_pattern,
)

__all__ = [
    # Discovery tools
    "create_file_manifest",
    "repomix_orientation",
    "repomix_bundle",
    "rg_search",
    "write_file_list",
    "read_file_bounded",
    # LSP tools
    "lsp_start",
    "lsp_shutdown",
    "lsp_document_symbols",
    "lsp_hover",
    "lsp_references",
    "lsp_definition",
    # ast-grep tools
    "astgrep_scan",
    "astgrep_scan_rule_pack",
    "astgrep_inline_rule",
    # Shell utilities
    "CommandResult",
    "ToolResult",
    "run_command",
    # Validation utilities
    "ValidationError",
    "validate_repo_path",
    "validate_file_path",
    "validate_glob_pattern",
    "validate_search_pattern",
]
