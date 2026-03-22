"""Framework detection patterns for entry point scoring boost.

Identifies framework-specific entry points (Next.js pages, FastAPI routes,
Django views, etc.) and provides scoring multipliers for find_entry_points().
"""

from __future__ import annotations

import fnmatch
import re
from typing import Any

from pydantic import Field

from code_context_agent.models.base import FrozenModel


class FrameworkPattern(FrozenModel):
    """A pattern that identifies framework-specific entry points."""

    framework: str
    file_glob: str  # e.g., "pages/**/*.tsx", "app/**/route.ts"
    symbol_pattern: str | None = None  # regex on symbol name
    entry_point_boost: float = Field(default=2.0, ge=1.0, le=10.0)


# Framework detection patterns
FRAMEWORK_PATTERNS: dict[str, list[FrameworkPattern]] = {
    "nextjs": [
        FrameworkPattern(framework="nextjs", file_glob="pages/**/*.tsx", entry_point_boost=3.0),
        FrameworkPattern(framework="nextjs", file_glob="pages/**/*.ts", entry_point_boost=3.0),
        FrameworkPattern(framework="nextjs", file_glob="app/**/page.tsx", entry_point_boost=3.0),
        FrameworkPattern(framework="nextjs", file_glob="app/**/route.ts", entry_point_boost=3.0),
        FrameworkPattern(framework="nextjs", file_glob="app/**/layout.tsx", entry_point_boost=2.0),
    ],
    "express": [
        FrameworkPattern(
            framework="express",
            file_glob="**/*.ts",
            symbol_pattern=r"app\.(get|post|put|delete|patch|use)",
            entry_point_boost=3.0,
        ),
        FrameworkPattern(
            framework="express",
            file_glob="**/*.js",
            symbol_pattern=r"app\.(get|post|put|delete|patch|use)",
            entry_point_boost=3.0,
        ),
        FrameworkPattern(framework="express", file_glob="**/routes/**/*", entry_point_boost=2.0),
    ],
    "django": [
        FrameworkPattern(framework="django", file_glob="**/views.py", entry_point_boost=3.0),
        FrameworkPattern(framework="django", file_glob="**/urls.py", entry_point_boost=2.5),
        FrameworkPattern(framework="django", file_glob="**/admin.py", entry_point_boost=2.0),
        FrameworkPattern(framework="django", file_glob="**/management/commands/**/*.py", entry_point_boost=3.0),
    ],
    "flask": [
        FrameworkPattern(
            framework="flask",
            file_glob="**/*.py",
            symbol_pattern=r"@app\.route",
            entry_point_boost=3.0,
        ),
        FrameworkPattern(
            framework="flask",
            file_glob="**/*.py",
            symbol_pattern=r"@blueprint\.route",
            entry_point_boost=3.0,
        ),
    ],
    "fastapi": [
        FrameworkPattern(
            framework="fastapi",
            file_glob="**/*.py",
            symbol_pattern=r"@(app|router)\.(get|post|put|delete|patch)",
            entry_point_boost=3.0,
        ),
        FrameworkPattern(framework="fastapi", file_glob="**/routers/**/*.py", entry_point_boost=2.0),
    ],
    "cli": [
        FrameworkPattern(
            framework="cli",
            file_glob="**/*.py",
            symbol_pattern=r"(^main$|^cli$|^__main__)",
            entry_point_boost=2.5,
        ),
        FrameworkPattern(framework="cli", file_glob="**/cli.py", entry_point_boost=2.5),
        FrameworkPattern(framework="cli", file_glob="**/__main__.py", entry_point_boost=3.0),
    ],
    "pytest": [
        FrameworkPattern(framework="pytest", file_glob="**/test_*.py", entry_point_boost=1.5),
        FrameworkPattern(framework="pytest", file_glob="**/*_test.py", entry_point_boost=1.5),
        FrameworkPattern(framework="pytest", file_glob="**/conftest.py", entry_point_boost=1.5),
    ],
}


def detect_frameworks(file_paths: list[str]) -> list[str]:
    """Detect frameworks present in the repository based on file paths.

    Args:
        file_paths: List of relative file paths in the repository.

    Returns:
        List of detected framework names (e.g., ["fastapi", "pytest"]).
    """
    detected: list[str] = []
    for framework, patterns in FRAMEWORK_PATTERNS.items():
        for pattern in patterns:
            if any(fnmatch.fnmatch(fp, pattern.file_glob) for fp in file_paths):
                detected.append(framework)
                break
    return detected


def get_entry_point_patterns(frameworks: list[str]) -> list[FrameworkPattern]:
    """Get all entry point patterns for detected frameworks."""
    patterns: list[FrameworkPattern] = []
    for fw in frameworks:
        patterns.extend(FRAMEWORK_PATTERNS.get(fw, []))
    return patterns


def score_entry_point(
    node_data: dict[str, Any],
    patterns: list[FrameworkPattern],
) -> float:
    """Score a node as a potential entry point based on framework patterns.

    Returns a boost multiplier (>= 1.0). Higher means more likely an entry point.
    """
    file_path = node_data.get("file_path", "")
    name = node_data.get("name", "")
    max_boost = 1.0

    for pattern in patterns:
        if not fnmatch.fnmatch(file_path, pattern.file_glob):
            continue
        if pattern.symbol_pattern:
            if re.search(pattern.symbol_pattern, name):
                max_boost = max(max_boost, pattern.entry_point_boost)
        else:
            max_boost = max(max_boost, pattern.entry_point_boost)

    return max_boost
