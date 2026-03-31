"""Clone detection tool for finding duplicate code across files.

Uses jscpd (JS Copy/Paste Detector) via npx to detect code clones.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from loguru import logger
from strands import tool

from .validation import ValidationError, validate_glob_pattern, validate_repo_path


@tool
def detect_clones(
    repo_path: str,
    min_lines: int = 5,
    min_tokens: int = 50,
    include_globs: str = "",
    threshold: int = 0,
) -> str:
    """Detect duplicate and near-duplicate code blocks across files.

    USE THIS TOOL:
    - To find copy-paste code that should be refactored into shared helpers
    - During code health analysis to measure duplication percentage
    - To identify cross-file verbatim matches

    DO NOT USE:
    - For finding specific known patterns (use rg_search or astgrep_scan)
    - On very small repos (<10 files) where duplication is unlikely

    Uses jscpd (JS Copy/Paste Detector) to find cloned code blocks.
    Results can be ingested into the code graph as SIMILAR_TO edges
    via code_graph_ingest_clones.

    Args:
        repo_path: Repository root path.
        min_lines: Minimum clone block size in lines (default 5).
        min_tokens: Minimum clone block size in tokens (default 50).
        include_globs: Comma-separated glob patterns (e.g., "**/*.py,**/*.ts").
        threshold: Minimum duplication percentage to report (0-100, 0 = all).

    Returns:
        JSON with clone groups containing file paths, line ranges, and similarity.

    Output Size: ~200 bytes per clone pair. Capped at 50 clones.
    """
    try:
        repo = validate_repo_path(repo_path)
    except ValidationError as e:
        return json.dumps({"status": "error", "error": str(e)})

    cmd = [
        "npx",
        "-y",
        "jscpd@4",
        "--reporters",
        "json",
        "--output",
        "/dev/stderr",
        "--min-lines",
        str(min_lines),
        "--min-tokens",
        str(min_tokens),
        "--blame",
        "false",
        str(repo),
    ]

    if include_globs:
        for raw_glob in include_globs.split(","):
            stripped = raw_glob.strip()
            if stripped:
                try:
                    validate_glob_pattern(stripped)
                except ValidationError as e:
                    return json.dumps({"status": "error", "error": str(e)})
                cmd.extend(["--pattern", stripped])

    if threshold > 0:
        cmd.extend(["--threshold", str(threshold)])

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "error", "error": "Clone detection timed out after 120s"})
    except (subprocess.SubprocessError, OSError) as e:
        return json.dumps({"status": "error", "error": str(e)})

    # jscpd writes JSON to stderr when --output /dev/stderr
    # Try stderr first, then stdout
    raw_json = proc.stderr or proc.stdout
    if not raw_json.strip():
        # No output means no clones found
        return json.dumps(
            {
                "status": "success",
                "total_clones": 0,
                "duplication_percentage": 0.0,
                "clones": [],
            },
        )

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        # jscpd may mix text output with JSON — try to extract JSON
        # Look for the JSON portion
        for raw_line in raw_json.splitlines():
            stripped_line = raw_line.strip()
            if stripped_line.startswith("{") or stripped_line.startswith("["):
                try:
                    data = json.loads(stripped_line)
                    break
                except json.JSONDecodeError:
                    continue
        else:
            logger.warning(f"Could not parse jscpd output: {raw_json[:500]}")
            return json.dumps(
                {
                    "status": "success",
                    "total_clones": 0,
                    "duplication_percentage": 0.0,
                    "clones": [],
                    "note": "jscpd output could not be parsed",
                },
            )

    # Parse jscpd JSON output
    duplicates = data.get("duplicates", [])
    statistics = data.get("statistics", {})

    clones = []
    for dup in duplicates[:50]:  # Cap at 50 clones
        first = dup.get("firstFile", {})
        second = dup.get("secondFile", {})

        first_file = first.get("name", "")
        second_file = second.get("name", "")

        # Make paths relative to repo
        try:
            first_file = str(Path(first_file).relative_to(repo))
        except ValueError:
            pass  # path is already relative or outside repo — keep as-is
        try:
            second_file = str(Path(second_file).relative_to(repo))
        except ValueError:
            pass  # path is already relative or outside repo — keep as-is

        clones.append(
            {
                "first_file": first_file,
                "first_start": first.get("start", 0),
                "first_end": first.get("end", 0),
                "second_file": second_file,
                "second_start": second.get("start", 0),
                "second_end": second.get("end", 0),
                "lines": dup.get("lines", 0),
                "tokens": dup.get("tokens", 0),
                "fragment": dup.get("fragment", "")[:200],
            },
        )

    total_percentage = statistics.get("total", {}).get("percentage", 0.0)

    return json.dumps(
        {
            "status": "success",
            "total_clones": len(clones),
            "duplication_percentage": round(total_percentage, 2),
            "clones": clones,
        },
    )
