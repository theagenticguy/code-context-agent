"""Custom tools package for code context analysis.

This package provides all tools used by the code context agent:
- Discovery: File manifests, repomix bundles, ripgrep search
- Git: History analysis, hotspots, coupling, contributors
- Shell: Bounded command execution
"""

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
