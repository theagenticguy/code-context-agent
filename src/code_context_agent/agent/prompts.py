"""Agent prompt rendering from Jinja2 templates.

This module renders system prompts and steering fragments from
Jinja2 templates in src/code_context_agent/templates/.
"""

from __future__ import annotations

from ..templates import render_prompt, render_steering


def get_prompt() -> str:
    """Render the unified system prompt.

    Returns:
        Rendered system prompt string from system.md.j2
    """
    return render_prompt("system.md.j2")


def get_steering_content(name: str) -> str:
    """Render a steering prompt fragment by name.

    Args:
        name: Fragment name (e.g., "size_limits", "conciseness",
              "anti_patterns", "tool_efficiency", "graph_exploration")

    Returns:
        Rendered steering content string
    """
    return render_steering(name)
