"""Agent orchestration package for code context analysis.

This package provides the core agent functionality:
- get_analysis_tools: Factory function to build the analysis tool list
- run_analysis: Async function to run analysis with event streaming
- Hooks: Quality guidance via standard HookProvider pattern
"""

from .factory import get_analysis_tools
from .runner import run_analysis, run_analysis_sync

__all__ = [
    "get_analysis_tools",
    "run_analysis",
    "run_analysis_sync",
]
