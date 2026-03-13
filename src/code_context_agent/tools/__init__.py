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
    repomix_bundle_with_context,
    repomix_compressed_signatures,
    repomix_json_export,
    repomix_orientation,
    repomix_split_bundle,
    rg_search,
    write_file,
    write_file_list,
)
from .git import (
    git_blame_summary,
    git_contributors,
    git_diff_file,
    git_file_history,
    git_files_changed_together,
    git_hotspots,
    git_recent_commits,
)
from .graph import (
    code_graph_analyze,
    code_graph_create,
    code_graph_explore,
    code_graph_export,
    code_graph_ingest_astgrep,
    code_graph_ingest_inheritance,
    code_graph_ingest_lsp,
    code_graph_ingest_rg,
    code_graph_ingest_tests,
    code_graph_load,
    code_graph_save,
    code_graph_stats,
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
    validate_path_within_repo,
    validate_repo_path,
    validate_search_pattern,
)

__all__ = [
    # Discovery tools
    "create_file_manifest",
    "repomix_orientation",
    "repomix_bundle",
    "repomix_bundle_with_context",
    "repomix_compressed_signatures",
    "repomix_json_export",
    "repomix_split_bundle",
    "rg_search",
    "write_file",
    "write_file_list",
    "read_file_bounded",
    # Git history tools
    "git_files_changed_together",
    "git_file_history",
    "git_recent_commits",
    "git_diff_file",
    "git_blame_summary",
    "git_hotspots",
    "git_contributors",
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
    # Graph tools
    "code_graph_create",
    "code_graph_ingest_lsp",
    "code_graph_ingest_astgrep",
    "code_graph_ingest_rg",
    "code_graph_ingest_inheritance",
    "code_graph_ingest_tests",
    "code_graph_analyze",
    "code_graph_explore",
    "code_graph_export",
    "code_graph_save",
    "code_graph_load",
    "code_graph_stats",
    # Shell utilities
    "CommandResult",
    "ToolResult",
    "run_command",
    # Validation utilities
    "ValidationError",
    "validate_repo_path",
    "validate_file_path",
    "validate_glob_pattern",
    "validate_path_within_repo",
    "validate_search_pattern",
]
