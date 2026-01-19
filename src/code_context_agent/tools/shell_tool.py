"""Shell tool with proper STDIO capture for agent tool responses.

This module provides a shell tool that properly captures stdout/stderr
and returns them to the agent as tool responses, rather than leaking
output to the terminal.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)

# Default timeout for shell commands (15 minutes)
DEFAULT_TIMEOUT = 900

# Maximum output size to capture (100KB)
MAX_OUTPUT_SIZE = 100_000


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
    from pathlib import Path

    if timeout is None:
        timeout = DEFAULT_TIMEOUT

    if work_dir is None:
        work_dir = str(Path.cwd())

    # Normalize command to list
    commands = [command] if isinstance(command, str) else command

    results = []
    has_errors = False

    for cmd in commands:
        try:
            # Run command with STDIO capture
            proc = subprocess.run(
                ["sh", "-c", cmd],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            stdout = proc.stdout[:MAX_OUTPUT_SIZE] if proc.stdout else ""
            stderr = proc.stderr[:MAX_OUTPUT_SIZE] if proc.stderr else ""

            # Truncation notice
            if proc.stdout and len(proc.stdout) > MAX_OUTPUT_SIZE:
                stdout += f"\n... (truncated, {len(proc.stdout)} total chars)"
            if proc.stderr and len(proc.stderr) > MAX_OUTPUT_SIZE:
                stderr += f"\n... (truncated, {len(proc.stderr)} total chars)"

            # Check for errors
            cmd_has_error = proc.returncode != 0 or stderr

            if cmd_has_error:
                has_errors = True

            result = {
                "command": cmd,
                "exit_code": proc.returncode,
                "status": "error" if cmd_has_error else "success",
                "stdout": stdout,
                "stderr": stderr,
            }
            results.append(result)

            # Stop on error unless ignore_errors is set
            if cmd_has_error and not ignore_errors:
                break

        except subprocess.TimeoutExpired:
            has_errors = True
            results.append(
                {
                    "command": cmd,
                    "exit_code": -1,
                    "status": "error",
                    "stdout": "",
                    "stderr": f"Command timed out after {timeout} seconds",
                }
            )
            if not ignore_errors:
                break

        except Exception as e:
            has_errors = True
            results.append(
                {
                    "command": cmd,
                    "exit_code": -1,
                    "status": "error",
                    "stdout": "",
                    "stderr": str(e),
                }
            )
            if not ignore_errors:
                break

    # Format content for agent
    content = []

    # Summary
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = len(results) - success_count

    content.append(
        {
            "text": f"Execution Summary:\n"
            f"Total commands: {len(results)}\n"
            f"Successful: {success_count}\n"
            f"Failed: {error_count}"
        }
    )

    # Individual results
    for result in results:
        text_parts = [
            f"Command: {result['command']}",
            f"Status: {result['status']}",
            f"Exit Code: {result['exit_code']}",
        ]

        if result["stdout"]:
            text_parts.append(f"Output:\n{result['stdout']}")

        if result["stderr"]:
            text_parts.append(f"Error:\n{result['stderr']}")

        content.append({"text": "\n".join(text_parts)})

    # Determine overall status
    if has_errors and not ignore_errors:
        return {"status": "error", "content": content}
    else:
        return {"status": "success", "content": content}
