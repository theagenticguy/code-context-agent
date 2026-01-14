"""Custom tools package for code context analysis."""

from .astgrep import astgrep_inline_rule, astgrep_scan, astgrep_scan_rule_pack
from .discovery import (
    create_file_manifest,
    read_file_bounded,
    repomix_bundle,
    repomix_orientation,
    rg_search,
    write_file_list,
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
