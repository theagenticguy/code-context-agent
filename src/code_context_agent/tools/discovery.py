"""Discovery tools for codebase analysis.

This module provides tools for file discovery, manifest creation, and
context bundling using external tools like ripgrep and repomix.
"""

from __future__ import annotations

import json
import logging
import shlex
from pathlib import Path

from strands import tool

from .shell import run_command

logger = logging.getLogger(__name__)


@tool
def create_file_manifest(repo_path: str) -> str:
    """Create ignore-aware file manifest using ripgrep.

    USE THIS TOOL: As the FIRST step in any codebase analysis workflow.
    Creates a safe inventory of files without reading contents.

    DO NOT USE:
    - If you already have a manifest from a previous call in this session
    - If .agent/files.all.txt exists and is recent

    Generates a list of all files in the repository, respecting .gitignore
    and skipping hidden/binary files. Output is written to .agent/files.all.txt.

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        JSON with:
        - manifest_path: Path to .agent/files.all.txt
        - file_count: Number of files found (typical: 100-5000)

    Output Size: ~100 bytes JSON + manifest file (~50 bytes per file path)

    Common Errors:
        - "rg not found": ripgrep not installed (install with: cargo install ripgrep)
        - Empty manifest: Check if repo_path is correct and contains files
        - Permission denied: Ensure read access to the repository

    Example success:
        {"status": "success", "manifest_path": "/repo/.agent/files.all.txt", "file_count": 847}
    """
    repo = Path(repo_path).resolve()
    agent_dir = repo / ".agent"
    agent_dir.mkdir(exist_ok=True)
    manifest_path = agent_dir / "files.all.txt"

    # Use ripgrep --files which respects .gitignore
    # Use sh -c for shell redirection with shlex.quote for path safety
    result = run_command(
        ["sh", "-c", f"rg --files > {shlex.quote(str(manifest_path))}"],
        cwd=str(repo),
    )

    if result["status"] != "success":
        return json.dumps(
            {
                "status": "error",
                "error": result["stderr"],
            }
        )

    # Count files
    try:
        file_count = sum(1 for _ in manifest_path.open())
    except Exception:
        file_count = 0

    logger.info(f"Created file manifest with {file_count} files")

    return json.dumps(
        {
            "status": "success",
            "manifest_path": str(manifest_path),
            "file_count": file_count,
        }
    )


@tool
def repomix_orientation(
    repo_path: str,
    token_threshold: int = 300,
    max_file_count: int = 10000,
) -> str:
    """Generate token-aware orientation snapshot without file contents.

    USE THIS TOOL: After create_file_manifest to understand codebase structure
    and identify high-complexity areas via token distribution.

    DO NOT USE:
    - If repo has >10K files (will auto-skip with recommendation)
    - If you only need to find specific files (use rg_search instead)
    - If .agent/CONTEXT.orientation.md exists and repo hasn't changed

    Uses repomix to create a metadata overview including directory structure
    and token distribution tree. Helps identify where code complexity lies
    without bundling actual content.

    Args:
        repo_path: Absolute path to the repository root.
        token_threshold: Minimum tokens to show in tree (filters noise).
        max_file_count: Maximum files allowed before skipping (default 10000).

    Returns:
        JSON with output path and status, or skipped status for large repos.

    Output Size:
        - Small repos (<500 files): ~5-20KB markdown
        - Medium repos (500-2000 files): ~20-100KB markdown
        - Large repos (2000-10000 files): ~100-500KB markdown
        - Execution time: 5-60 seconds depending on repo size

    Common Errors:
        - "repomix not found": Install with npm install -g repomix
        - "skipped" status: Repo exceeds max_file_count, use --include patterns
        - Timeout after 180s: Repo too large, reduce scope with glob patterns

    Example success:
        {"status": "success", "output_path": "/repo/.agent/CONTEXT.orientation.md"}

    Example skipped:
        {"status": "skipped", "reason": "Repository has 15000 files (max: 10000)"}
    """
    repo = Path(repo_path).resolve()
    agent_dir = repo / ".agent"
    agent_dir.mkdir(exist_ok=True)
    output_path = agent_dir / "CONTEXT.orientation.md"

    # Pre-check file count to avoid long-running operations on large repos
    # Use cwd instead of embedding path in command to avoid shell escaping issues
    count_result = run_command(
        ["sh", "-c", "rg --files | wc -l"],
        cwd=str(repo),
        timeout=10,
    )

    if count_result["status"] == "success":
        try:
            file_count = int(count_result["stdout"].strip())
            if file_count > max_file_count:
                logger.warning(f"Repository has {file_count} files, exceeding max of {max_file_count}")
                return json.dumps(
                    {
                        "status": "skipped",
                        "reason": f"Repository has {file_count} files (max: {max_file_count})",
                        "recommendation": "Use --include patterns to limit scope",
                    }
                )
        except ValueError:
            pass  # Proceed if we can't parse count

    cmd = [
        "repomix",
        "--no-files",
        "--style",
        "markdown",
        "--token-count-tree",
        "--token-count-tree-threshold",
        str(token_threshold),
        "-o",
        str(output_path),
        str(repo),
    ]

    result = run_command(cmd, cwd=str(repo), timeout=180)

    if result["status"] != "success":
        return json.dumps(
            {
                "status": "error",
                "error": result["stderr"],
                "stdout": result["stdout"],
            }
        )

    logger.info(f"Created orientation snapshot: {output_path}")

    return json.dumps(
        {
            "status": "success",
            "output_path": str(output_path),
        }
    )


@tool
def repomix_bundle(file_list_path: str, output_path: str, compress: bool = True) -> str:
    """Pack curated files into markdown context bundle.

    Takes a list of file paths and bundles their contents into a single
    markdown file using repomix. The --stdin flag reads paths from the
    provided file list.

    Args:
        file_list_path: Path to file containing paths to pack (one per line).
        output_path: Output markdown file path.
        compress: Use tree-sitter compression to reduce size.

    Returns:
        JSON with output path and status.

    Example:
        >>> result = repomix_bundle(".agent/files.targeted.txt", ".agent/CONTEXT.bundle.md")
    """
    file_list = Path(file_list_path).resolve()
    output = Path(output_path).resolve()

    if not file_list.exists():
        return json.dumps(
            {
                "status": "error",
                "error": f"File list not found: {file_list}",
            }
        )

    compress_flag = "--compress" if compress else ""

    # Use sh -c for shell pipe - build command with shlex.quote for safety
    repomix_args = f"--stdin --style markdown --output-show-line-numbers {compress_flag}"
    shell_cmd = f"cat {shlex.quote(str(file_list))} | repomix {repomix_args} -o {shlex.quote(str(output))}"
    cmd = ["sh", "-c", shell_cmd]

    result = run_command(cmd, timeout=300)

    if result["status"] != "success":
        return json.dumps(
            {
                "status": "error",
                "error": result["stderr"],
                "stdout": result["stdout"],
            }
        )

    # Get file size
    try:
        file_size = output.stat().st_size
    except Exception:
        file_size = 0

    logger.info(f"Created context bundle: {output} ({file_size} bytes)")

    return json.dumps(
        {
            "status": "success",
            "output_path": str(output),
            "file_size_bytes": file_size,
        }
    )


@tool
def rg_search(
    pattern: str,
    repo_path: str,
    glob: str | None = None,
    file_type: str | None = None,
    max_count: int = 100,
    context_lines: int = 0,
) -> str:
    """Search for pattern in repository using ripgrep.

    USE THIS TOOL:
    - To find entrypoints (e.g., "def main", "createServer", "app.listen")
    - To locate specific functions, classes, or patterns
    - To discover imports and dependencies
    - When you know WHAT to search for but not WHERE

    DO NOT USE:
    - For listing all files (use create_file_manifest instead)
    - For reading file contents (use read_file_bounded instead)
    - For structural analysis (use lsp_document_symbols instead)

    Args:
        pattern: Regex pattern to search for.
        repo_path: Repository root path.
        glob: Optional glob filter (e.g., "*.py", "src/**/*.ts").
        file_type: Optional file type (e.g., "py", "ts", "js").
        max_count: Maximum matches to return per file (default 100).
        context_lines: Lines of context around matches (0-5 recommended).

    Returns:
        JSON with matches array containing path, line_number, and lines.

    Output Size: ~200 bytes per match. Results capped at 500 lines.

    Pattern Tips:
        - Literal strings: "createServer" (no regex escaping needed)
        - Function definitions: "def \\w+\\(" or "function \\w+\\("
        - Class definitions: "class \\w+"
        - Imports: "^import|^from .* import"
        - Case insensitive: Use "(?i)pattern"

    Common Errors:
        - "rg not found": ripgrep not installed
        - Empty matches with valid pattern: Try broader glob or check file_type
        - Regex syntax error: Escape special chars like ( ) [ ] { }

    Example success:
        {"status": "success", "pattern": "def main", "matches": [...], "match_count": 3}

    Example searches:
        >>> rg_search("def main", "/repo", glob="*.py")  # Python entrypoints
        >>> rg_search("createServer", "/repo", file_type="ts")  # TS server setup
        >>> rg_search("TODO|FIXME", "/repo", context_lines=2)  # Find todos with context
    """
    repo = Path(repo_path).resolve()

    # Build ripgrep command parts for shell execution with proper escaping
    cmd_parts = ["rg", "--json", f"-m {max_count}"]

    if glob:
        cmd_parts.append(f"-g {shlex.quote(glob)}")
    if file_type:
        cmd_parts.append(f"-t {shlex.quote(file_type)}")
    if context_lines > 0:
        cmd_parts.append(f"-C {context_lines}")

    cmd_parts.append(shlex.quote(pattern))
    cmd_parts.append(shlex.quote(str(repo)))

    # Use sh -c for shell pipe
    cmd = ["sh", "-c", " ".join(cmd_parts) + " | head -500"]

    result = run_command(cmd, cwd=str(repo), timeout=60)

    # Parse JSON lines output
    matches = []
    if result["stdout"]:
        for line in result["stdout"].strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data.get("data", {})
                    matches.append(
                        {
                            "path": match_data.get("path", {}).get("text", ""),
                            "line_number": match_data.get("line_number"),
                            "lines": match_data.get("lines", {}).get("text", ""),
                        }
                    )
            except json.JSONDecodeError:
                continue

    return json.dumps(
        {
            "status": "success" if result["return_code"] in (0, 1) else "error",  # rg returns 1 for no matches
            "pattern": pattern,
            "matches": matches,
            "match_count": len(matches),
        }
    )


@tool
def write_file_list(file_paths: list[str], output_path: str) -> str:
    """Write a list of file paths to a file for repomix bundling.

    Use this to create the curated file list before calling repomix_bundle.

    Args:
        file_paths: List of file paths to include in the bundle.
        output_path: Path to write the file list.

    Returns:
        JSON with output path and file count.

    Example:
        >>> result = write_file_list(["src/main.ts", "src/utils.ts"], ".agent/files.targeted.txt")
    """
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    # Deduplicate and sort
    unique_paths = sorted(set(file_paths))

    with output.open("w") as f:
        for path in unique_paths:
            f.write(f"{path}\n")

    logger.info(f"Wrote {len(unique_paths)} paths to {output}")

    return json.dumps(
        {
            "status": "success",
            "output_path": str(output),
            "file_count": len(unique_paths),
        }
    )


@tool
def read_file_bounded(file_path: str, max_lines: int = 500, start_line: int = 1) -> str:
    """Read a file with bounded output for safe analysis.

    USE THIS TOOL:
    - To read a SINGLE specific file when you know the exact path
    - To inspect implementation details after finding via rg_search
    - To read configuration files (package.json, pyproject.toml, etc.)
    - When you need line numbers for subsequent LSP calls

    DO NOT USE:
    - To read multiple files at once (use repomix_bundle instead)
    - For initial exploration (use repomix_orientation first)
    - For very large files (>1000 lines) without specifying start_line

    Reads file contents with line limits to prevent token overflow.
    Includes line numbers formatted as "  123| code here".

    Args:
        file_path: Absolute path to the file.
        max_lines: Maximum lines to read (default 500, reduce for large files).
        start_line: Starting line number (1-indexed, use for pagination).

    Returns:
        JSON with content (with line numbers), path, lines_read, and truncated flag.

    Output Size: ~80 bytes per line average. 500 lines = ~40KB.

    Common Errors:
        - "File not found": Check path is absolute and file exists
        - "truncated": true: File has more lines, use start_line to paginate
        - UnicodeDecodeError: File is binary, not suitable for text reading

    Example success:
        {"status": "success", "path": "/repo/src/main.py", "content": "     1| ...",
         "start_line": 1, "lines_read": 150, "truncated": false}

    Example pagination (reading lines 500-1000):
        >>> read_file_bounded("/repo/large_file.py", max_lines=500, start_line=500)
    """
    path = Path(file_path).resolve()

    if not path.exists():
        return json.dumps(
            {
                "status": "error",
                "error": f"File not found: {path}",
            }
        )

    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            lines = []
            for i, line in enumerate(f, 1):
                if i < start_line:
                    continue
                if i >= start_line + max_lines:
                    break
                lines.append(f"{i:6d}| {line.rstrip()}")

        content = "\n".join(lines)
        total_lines_read = len(lines)

        return json.dumps(
            {
                "status": "success",
                "path": str(path),
                "content": content,
                "start_line": start_line,
                "lines_read": total_lines_read,
                "truncated": total_lines_read >= max_lines,
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
            }
        )
