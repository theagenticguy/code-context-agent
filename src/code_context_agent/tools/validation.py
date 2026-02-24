"""Input validation utilities for tool functions.

This module provides validation functions to prevent path traversal,
command injection, and other security issues in user-provided inputs.
"""

from __future__ import annotations

import re
from pathlib import Path


class ValidationError(ValueError):
    """Raised when input validation fails."""


def validate_repo_path(path: str) -> Path:
    """Validate repository path is safe to use.

    Args:
        path: User-provided path string.

    Returns:
        Resolved Path object.

    Raises:
        ValidationError: If path is dangerous or invalid.

    Example:
        >>> validate_repo_path("/home/user/project")
        PosixPath('/home/user/project')
    """
    resolved = Path(path).resolve()

    # Prevent path traversal
    if ".." in path:
        raise ValidationError(f"Path traversal detected: {path}")

    # Prevent system paths
    dangerous = {"/", "/etc", "/usr", "/var", "/bin", "/sbin", "/root", "/boot"}
    if str(resolved) in dangerous:
        raise ValidationError(f"Dangerous system path: {path}")

    # Must exist and be directory
    if not resolved.exists():
        raise ValidationError(f"Path does not exist: {path}")
    if not resolved.is_dir():
        raise ValidationError(f"Path is not a directory: {path}")

    return resolved


def validate_file_path(path: str, must_exist: bool = True) -> Path:
    """Validate file path is safe.

    Args:
        path: User-provided file path.
        must_exist: If True, file must exist.

    Returns:
        Resolved Path object.

    Raises:
        ValidationError: If path is dangerous or invalid.
    """
    resolved = Path(path).resolve()

    # Prevent path traversal
    if ".." in path:
        raise ValidationError(f"Path traversal detected: {path}")

    # Must exist if required
    if must_exist and not resolved.exists():
        raise ValidationError(f"File does not exist: {path}")

    # Must be file if exists
    if resolved.exists() and not resolved.is_file():
        raise ValidationError(f"Path is not a file: {path}")

    return resolved


def validate_glob_pattern(pattern: str) -> str:
    """Validate glob pattern is safe.

    Args:
        pattern: User-provided glob pattern.

    Returns:
        Validated pattern string.

    Raises:
        ValidationError: If pattern contains dangerous characters.
    """
    # Prevent command injection via glob
    dangerous_chars = re.compile(r"[;&|`$(){}\\]")
    if dangerous_chars.search(pattern):
        raise ValidationError(f"Invalid characters in pattern: {pattern}")

    # Prevent path traversal
    if ".." in pattern:
        raise ValidationError(f"Path traversal in pattern: {pattern}")

    return pattern


def validate_search_pattern(pattern: str, max_length: int = 1000) -> str:
    """Validate search pattern (regex) is safe.

    Args:
        pattern: User-provided search pattern.
        max_length: Maximum allowed pattern length.

    Returns:
        Validated pattern string.

    Raises:
        ValidationError: If pattern is invalid or too long.
    """
    if len(pattern) > max_length:
        raise ValidationError(f"Pattern too long: {len(pattern)} > {max_length}")

    # Try to compile regex to catch syntax errors early
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValidationError(f"Invalid regex pattern: {e}") from e

    return pattern
