"""Shell tool with proper STDIO capture for agent tool responses.

This module provides a shell tool that properly captures stdout/stderr
and returns them to the agent as tool responses, rather than leaking
output to the terminal.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, computed_field
from strands import tool

# Default timeout for shell commands (15 minutes)
DEFAULT_TIMEOUT = 900

# Maximum output size to capture (100KB)
MAX_OUTPUT_SIZE = 100_000


class CommandResult(BaseModel):
    """Result of a shell command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float = 0.0

    @computed_field
    @property
    def success(self) -> bool:
        """Command succeeded if exit code is 0 and no stderr."""
        return self.exit_code == 0 and not self.stderr

    @computed_field
    @property
    def status(self) -> str:
        """Status string for display."""
        return "success" if self.success else "error"


def _truncate_output(text: str, max_size: int) -> tuple[str, bool]:
    """Truncate output if needed.

    Args:
        text: Output text to truncate
        max_size: Maximum size in characters

    Returns:
        Tuple of (truncated_text, was_truncated)
    """
    if not text or len(text) <= max_size:
        return text, False

    truncated = text[:max_size]
    truncated += f"\n... (truncated, {len(text)} total chars)"
    return truncated, True


def _execute_single_command(
    cmd: str,
    work_dir: str,
    timeout: int,
) -> CommandResult:
    """Execute one command and return structured result.

    Args:
        cmd: Command string to execute
        work_dir: Working directory
        timeout: Timeout in seconds

    Returns:
        CommandResult with execution details
    """
    start_time = time.time()

    try:
        proc = subprocess.run(
            ["sh", "-c", cmd],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Truncate outputs if needed
        stdout, _ = _truncate_output(
            proc.stdout or "",
            MAX_OUTPUT_SIZE,
        )
        stderr, _ = _truncate_output(
            proc.stderr or "",
            MAX_OUTPUT_SIZE,
        )

        execution_time = time.time() - start_time

        return CommandResult(
            command=cmd,
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            execution_time=execution_time,
        )

    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        return CommandResult(
            command=cmd,
            exit_code=-1,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
            execution_time=execution_time,
        )

    except Exception as e:
        execution_time = time.time() - start_time
        logger.exception(f"Command execution failed: {cmd}")
        return CommandResult(
            command=cmd,
            exit_code=-1,
            stdout="",
            stderr=str(e),
            execution_time=execution_time,
        )


def _format_results(results: list[CommandResult]) -> dict[str, Any]:
    """Build the final response structure.

    Args:
        results: List of command results

    Returns:
        Dict with status and content blocks
    """
    content = []

    # Summary block
    success_count = sum(1 for r in results if r.success)
    error_count = len(results) - success_count

    content.append(
        {
            "text": f"Execution Summary:\n"
            f"Total commands: {len(results)}\n"
            f"Successful: {success_count}\n"
            f"Failed: {error_count}",
        },
    )

    # Individual result blocks
    for result in results:
        text_parts = [
            f"Command: {result.command}",
            f"Status: {result.status}",
            f"Exit Code: {result.exit_code}",
        ]

        if result.stdout:
            text_parts.append(f"Output:\n{result.stdout}")

        if result.stderr:
            text_parts.append(f"Error:\n{result.stderr}")

        content.append({"text": "\n".join(text_parts)})

    return {"content": content}


@tool
def shell(
    command: str | list[str],
    work_dir: str | None = None,
    timeout: int | None = None,
    ignore_errors: bool = False,
) -> dict[str, Any]:
    """Execute shell commands with proper STDIO capture.

    USE THIS TOOL:
    - For running shell commands (ls, git, npm, etc.)
    - When you need command output for analysis
    - For build and test commands

    DO NOT USE:
    - For reading file contents (use read_file_bounded instead)
    - For searching code (use rg_search instead)

    All stdout and stderr are captured and returned in the tool response.
    If stderr contains content or the exit code is non-zero, the tool
    returns an error status with a descriptive message.

    Args:
        command: Shell command string or list of commands to execute sequentially.
        work_dir: Working directory for command execution (default: current dir).
        timeout: Timeout in seconds for command execution (default: 900).
        ignore_errors: If True, continue on errors and return success (default: False).

    Returns:
        Dict containing:
        - status: "success" or "error"
        - content: List of text blocks with command results

    Example:
        >>> shell("ls -la")
        >>> shell(["git status", "git diff"], work_dir="/repo")
        >>> shell("npm test", timeout=300, ignore_errors=True)
    """
    # Set defaults
    if timeout is None:
        timeout = DEFAULT_TIMEOUT

    if work_dir is None:
        work_dir = str(Path.cwd())

    # Normalize command to list
    commands = [command] if isinstance(command, str) else command

    # Execute commands
    results = []
    for cmd in commands:
        result = _execute_single_command(cmd, work_dir, timeout)
        results.append(result)

        # Stop on error unless ignore_errors is set
        if not result.success and not ignore_errors:
            break

    # Format response
    response = _format_results(results)

    # Determine overall status
    has_errors = any(not r.success for r in results)
    if has_errors and not ignore_errors:
        response["status"] = "error"
    else:
        response["status"] = "success"

    return response
