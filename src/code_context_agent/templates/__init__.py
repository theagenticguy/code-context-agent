"""Jinja2 template loading and rendering for agent prompts.

This module provides a configured Jinja2 environment for rendering
prompt templates. Templates are loaded from this directory using
FileSystemLoader with StrictUndefined to catch missing variables.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


@lru_cache(maxsize=1)
def _get_environment() -> Environment:
    """Get the configured Jinja2 environment (cached singleton)."""
    template_dir = Path(__file__).parent
    return Environment(  # noqa: S701 - autoescape not needed for prompt templates
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_prompt(template_name: str, **context: Any) -> str:
    """Render a prompt template with the given context.

    Args:
        template_name: Template filename (e.g., "system.md.j2")
        **context: Variables to pass to the template

    Returns:
        Rendered prompt string
    """
    env = _get_environment()
    template = env.get_template(template_name)
    return template.render(**context)


def render_steering(name: str, **context: Any) -> str:
    """Render a steering template fragment.

    Args:
        name: Steering template name (e.g., "size_limits")
        **context: Variables to pass to the template

    Returns:
        Rendered steering prompt fragment
    """
    return render_prompt(f"steering/_{name}.md.j2", **context)
