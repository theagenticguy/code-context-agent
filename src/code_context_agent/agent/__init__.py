"""Agent orchestration package for code context analysis.

This package provides the core agent functionality:
- create_agent: Factory function to create configured analysis agents
- run_analysis: Async function to run analysis with event streaming
- get_prompt: Dynamic prompt rendering from Jinja2 templates
- Hooks: Quality guidance via standard HookProvider pattern
"""

from .factory import create_agent, get_analysis_tools
from .prompts import get_prompt
from .runner import run_analysis, run_analysis_sync

__all__ = [
    "create_agent",
    "get_analysis_tools",
    "get_prompt",
    "run_analysis",
    "run_analysis_sync",
]
