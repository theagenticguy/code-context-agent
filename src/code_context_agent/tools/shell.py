"""Unified shell command executor.

This module provides a secure, bounded shell command execution utility
shared across all tool modules.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any, TypedDict

from ..models.base import FrozenModel


class CommandResult(TypedDict):
    """Result of a shell command execution."""

    status: str
    stdout: str
    stderr: str
    return_code: int
    truncated: bool


class ToolResult(FrozenModel):
    """Standardized result structure for tool responses.

    Provides a consistent JSON serialization pattern for tool outputs.

    Example:
        >>> result = ToolResult(status="success", data={"count": 42})
        >>> return result.to_json()
        '{"status": "success", "data": {"count": 42}}'

        >>> result = ToolResult.error("File not found")
        >>> return result.to_json()
        '{"status": "error", "error": "File not found"}'
    """

    status: str
    data: dict[str, Any] | None = None
    error_message: str | None = None

    def to_json(self) -> str:
        """Serialize to JSON string, omitting None values."""
        d: dict[str, Any] = {"status": self.status}
        if self.data:
            d.update(self.data)
        if self.error_message:
            d["error"] = self.error_message
        return json.dumps(d)

    @classmethod
    def success(cls, **data: Any) -> ToolResult:
        """Create a success result with data."""
        return cls(status="success", data=data if data else None)

    @classmethod
    def error(cls, message: str, **extra: Any) -> ToolResult:
        """Create an error result."""
        return cls(status="error", error_message=message, data=extra if extra else None)


def run_command(
    cmd: str | list[str],
    cwd: str | None = None,
    timeout: int = 120,
    max_output: int = 100_000,
    input_data: str | None = None,
) -> CommandResult:
    """Run shell command with bounds.

    Uses shell=False with shlex parsing for security. For commands requiring
    shell features (pipes, redirects), pass a list like ["sh", "-c", "cmd"].

    Args:
        cmd: Command string or list of arguments.
        cwd: Working directory.
        timeout: Maximum execution time in seconds.
        max_output: Maximum characters to capture.
        input_data: Optional string to send to stdin.

    Returns:
        Dict with status, stdout, stderr, return_code, and truncated flag.
    """
    # Convert string to list safely using ternary for clarity
    cmd_list = shlex.split(cmd) if isinstance(cmd, str) else cmd

    try:
        result = subprocess.run(
            cmd_list,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_data,
        )

        stdout = result.stdout[:max_output]
        truncated = len(result.stdout) > max_output

        if truncated:
            stdout += f"\n... (truncated, {len(result.stdout)} total chars)"

        return {
            "status": "success" if result.returncode == 0 else "error",
            "stdout": stdout,
            "stderr": result.stderr[:10000],
            "return_code": result.returncode,
            "truncated": truncated,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "return_code": -1,
            "truncated": False,
        }
    except (subprocess.SubprocessError, OSError) as e:
        return {
            "status": "error",
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
            "truncated": False,
        }
