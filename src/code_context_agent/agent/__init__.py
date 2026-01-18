"""Agent orchestration package for code context analysis.

This package provides the core agent functionality:
- create_agent: Factory function to create configured analysis agents
- run_analysis: Async function to run analysis with event streaming
- FAST_PROMPT / DEEP_PROMPT: System prompts for each analysis mode
- Steering: Optional progressive disclosure handlers
"""

from .factory import create_agent, get_analysis_tools
from .runner import run_analysis, run_analysis_sync
from .sop import (
    ASTGREP_USAGE,
    BUSINESS_LOGIC_DEFINITION,
    CORE_RULES,
    DEEP_PROMPT,
    FAST_PROMPT,
    OUTPUT_FORMAT,
)

__all__ = [
    # Agent factory
    "create_agent",
    "get_analysis_tools",
    # Runner functions
    "run_analysis",
    "run_analysis_sync",
    # Prompts
    "FAST_PROMPT",
    "DEEP_PROMPT",
    # Prompt components (for custom composition)
    "CORE_RULES",
    "BUSINESS_LOGIC_DEFINITION",
    "OUTPUT_FORMAT",
    "ASTGREP_USAGE",
]
