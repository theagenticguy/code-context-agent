"""ast-grep tools for structural code analysis.

This module provides tools for running ast-grep structural searches
to find patterns like DB calls, state mutations, and API endpoints.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from strands import tool

from .validation import ValidationError, validate_glob_pattern, validate_repo_path

# Path to rule files relative to this module
RULES_DIR = Path(__file__).parent.parent / "rules"


@tool
def astgrep_scan(
    language: str,
    pattern: str,
    repo_path: str,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    max_results: int = 100,
) -> str:
    """Run ast-grep structural search with a pattern.

    Performs AST-based structural code search, which is more precise than
    regex for finding code patterns like function calls, assignments, etc.

    Args:
        language: Language identifier ("ts", "tsx", "py", "js", "jsx").
        pattern: ast-grep pattern (e.g., "$OBJ.$METHOD($$ARGS)").
        repo_path: Repository root path.
        include_globs: Paths to include (e.g., ["src/**", "apps/**"]).
        exclude_globs: Paths to exclude (e.g., ["**/node_modules/**"]).
        max_results: Maximum results to return.

    Returns:
        JSON array of matches with file, range, and matched text.

    Example:
        >>> result = astgrep_scan("ts", "$DB.query($$ARGS)", "/path/to/repo")
        >>> result = astgrep_scan("py", "$OBJ.execute($$SQL)", "/path/to/repo", include_globs=["src/**"])
    """
    try:
        repo = validate_repo_path(repo_path)
    except ValidationError as e:
        return json.dumps({"status": "error", "error": str(e)})

    # Build command as list (no shell)
    cmd_list = [
        "ast-grep",
        "run",
        "-l",
        language,
        "-p",
        pattern,
        "--json=stream",
    ]

    # Add globs
    if include_globs:
        for glob in include_globs:
            try:
                validate_glob_pattern(glob)
            except ValidationError as e:
                return json.dumps({"status": "error", "error": str(e)})
            cmd_list.extend(["--globs", glob])

    if exclude_globs:
        for glob in exclude_globs:
            try:
                validate_glob_pattern(glob)
            except ValidationError as e:
                return json.dumps({"status": "error", "error": str(e)})
            cmd_list.extend(["--globs", f"!{glob}"])

    cmd_list.append(str(repo))

    # Run directly without shell
    try:
        proc_result = subprocess.run(
            cmd_list,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Limit output lines after capture to avoid broken pipe
        stdout_lines = proc_result.stdout.split("\n")[: max_results * 10]
        result = {
            "status": "success" if proc_result.returncode == 0 else "error",
            "stdout": "\n".join(stdout_lines),
            "stderr": proc_result.stderr[:10000] if proc_result.stderr else "",
            "return_code": proc_result.returncode,
        }
    except subprocess.TimeoutExpired:
        result = {
            "status": "error",
            "stdout": "",
            "stderr": "Command timed out",
            "return_code": -1,
        }
    except (subprocess.SubprocessError, OSError) as e:
        result = {
            "status": "error",
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
        }

    # Parse streaming JSON output
    matches = []
    if result["stdout"]:
        for line in result["stdout"].strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                matches.append(
                    {
                        "file": data.get("file", ""),
                        "range": data.get("range", {}),
                        "text": data.get("text", ""),
                        "rule_id": data.get("ruleId", ""),
                    },
                )
                if len(matches) >= max_results:
                    break
            except json.JSONDecodeError:
                continue

    return json.dumps(
        {
            "status": "success" if matches or result["return_code"] == 0 else "no_matches",
            "language": language,
            "pattern": pattern,
            "matches": matches,
            "match_count": len(matches),
        },
    )


@tool
def astgrep_scan_rule_pack(
    rule_pack: str,
    repo_path: str,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    max_results: int = 200,
) -> str:
    """Run ast-grep with a predefined rule pack for business logic detection.

    Rule packs are YAML files with multiple rules for detecting specific
    patterns like DB calls, state mutations, and API interactions.

    Available rule packs:
    - "ts_business_logic": TypeScript/JavaScript DB, state, API patterns
    - "py_business_logic": Python DB, state, HTTP patterns

    Args:
        rule_pack: Name of the rule pack to use.
        repo_path: Repository root path.
        include_globs: Paths to include.
        exclude_globs: Paths to exclude.
        max_results: Maximum results to return.

    Returns:
        JSON array of matches grouped by rule ID.

    Example:
        >>> result = astgrep_scan_rule_pack("ts_business_logic", "/path/to/repo")
    """
    try:
        repo = validate_repo_path(repo_path)
    except ValidationError as e:
        return json.dumps({"status": "error", "error": str(e)})

    # Find rule file
    rule_file = RULES_DIR / f"{rule_pack}.yml"
    if not rule_file.exists():
        available = [f.stem for f in RULES_DIR.glob("*.yml")]
        return json.dumps(
            {
                "status": "error",
                "error": f"Rule pack not found: {rule_pack}. Available: {available}",
            },
        )

    # Build command as list (no shell)
    cmd_list = [
        "ast-grep",
        "scan",
        "--config",
        str(rule_file),
        "--json=stream",
    ]

    # Add globs
    if include_globs:
        for glob in include_globs:
            try:
                validate_glob_pattern(glob)
            except ValidationError as e:
                return json.dumps({"status": "error", "error": str(e)})
            cmd_list.extend(["--globs", glob])

    if exclude_globs:
        for glob in exclude_globs:
            try:
                validate_glob_pattern(glob)
            except ValidationError as e:
                return json.dumps({"status": "error", "error": str(e)})
            cmd_list.extend(["--globs", f"!{glob}"])

    cmd_list.append(str(repo))

    # Run directly without shell
    try:
        proc_result = subprocess.run(
            cmd_list,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Limit output lines after capture to avoid broken pipe
        stdout_lines = proc_result.stdout.split("\n")[: max_results * 10]
        result = {
            "status": "success" if proc_result.returncode == 0 else "error",
            "stdout": "\n".join(stdout_lines),
            "stderr": proc_result.stderr[:10000] if proc_result.stderr else "",
            "return_code": proc_result.returncode,
        }
    except subprocess.TimeoutExpired:
        result = {
            "status": "error",
            "stdout": "",
            "stderr": "Command timed out",
            "return_code": -1,
        }
    except (subprocess.SubprocessError, OSError) as e:
        result = {
            "status": "error",
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
        }

    # Parse streaming JSON output and group by rule
    matches_by_rule: dict[str, list[dict]] = {}
    total_count = 0

    if result["stdout"]:
        for line in result["stdout"].strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                rule_id = data.get("ruleId", "unknown")
                match = {
                    "file": data.get("file", ""),
                    "range": data.get("range", {}),
                    "text": data.get("text", ""),
                    "message": data.get("message", ""),
                }
                if rule_id not in matches_by_rule:
                    matches_by_rule[rule_id] = []
                matches_by_rule[rule_id].append(match)
                total_count += 1
                if total_count >= max_results:
                    break
            except json.JSONDecodeError:
                continue

    return json.dumps(
        {
            "status": "success" if matches_by_rule or result["return_code"] == 0 else "no_matches",
            "rule_pack": rule_pack,
            "matches_by_rule": matches_by_rule,
            "total_count": total_count,
            "rule_count": len(matches_by_rule),
        },
    )


@tool
def astgrep_inline_rule(
    language: str,
    rule_yaml: str,
    repo_path: str,
    include_globs: list[str] | None = None,
    max_results: int = 100,
) -> str:
    """Run ast-grep with an inline YAML rule definition.

    Use this for custom one-off patterns that aren't in the predefined
    rule packs.

    Args:
        language: Language identifier.
        rule_yaml: Inline YAML rule definition.
        repo_path: Repository root path.
        include_globs: Paths to include.
        max_results: Maximum results.

    Returns:
        JSON array of matches.

    Example:
        >>> rule = '''
        ... id: find-fetch
        ... language: TypeScript
        ... rule:
        ...   pattern: fetch($$ARGS)
        ... '''
        >>> result = astgrep_inline_rule("ts", rule, "/path/to/repo")
    """
    try:
        repo = validate_repo_path(repo_path)
    except ValidationError as e:
        return json.dumps({"status": "error", "error": str(e)})

    # Build command as list (no shell)
    cmd_list = [
        "ast-grep",
        "scan",
        "--inline-rules",
        rule_yaml,
        "--json=stream",
    ]

    if include_globs:
        for glob in include_globs:
            try:
                validate_glob_pattern(glob)
            except ValidationError as e:
                return json.dumps({"status": "error", "error": str(e)})
            cmd_list.extend(["--globs", glob])

    cmd_list.append(str(repo))

    # Run directly without shell
    try:
        proc_result = subprocess.run(
            cmd_list,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Limit output lines after capture to avoid broken pipe
        stdout_lines = proc_result.stdout.split("\n")[: max_results * 10]
        result = {
            "status": "success" if proc_result.returncode == 0 else "error",
            "stdout": "\n".join(stdout_lines),
            "stderr": proc_result.stderr[:10000] if proc_result.stderr else "",
            "return_code": proc_result.returncode,
        }
    except subprocess.TimeoutExpired:
        result = {
            "status": "error",
            "stdout": "",
            "stderr": "Command timed out",
            "return_code": -1,
        }
    except (subprocess.SubprocessError, OSError) as e:
        result = {
            "status": "error",
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
        }

    # Parse results
    matches = []
    if result["stdout"]:
        for line in result["stdout"].strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                matches.append(
                    {
                        "file": data.get("file", ""),
                        "range": data.get("range", {}),
                        "text": data.get("text", ""),
                    },
                )
                if len(matches) >= max_results:
                    break
            except json.JSONDecodeError:
                continue

    return json.dumps(
        {
            "status": "success" if matches or result["return_code"] == 0 else "no_matches",
            "language": language,
            "matches": matches,
            "match_count": len(matches),
        },
    )
