"""CI/CD integration templates for code-context-agent.

Provides ready-to-use workflow templates for GitHub Actions and GitLab CI
with three analysis cadences: nightly full, on-merge incremental, PR verdict.
"""

from __future__ import annotations

from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def render_github_actions() -> str:
    """Return the GitHub Actions workflow template content."""
    return (_TEMPLATES_DIR / "github_actions.yml").read_text()


def render_gitlab_ci() -> str:
    """Return the GitLab CI template content."""
    return (_TEMPLATES_DIR / "gitlab_ci.yml").read_text()
