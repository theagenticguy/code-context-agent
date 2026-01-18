"""Optional steering handlers for progressive disclosure.

This module provides LLMSteeringHandler instances that can be added to the agent
for contextual guidance at specific points during execution.

Usage:
    from strands import Agent
    from code_context_agent.agent.steering import (
        create_output_steering_handler,
        create_tool_steering_handler,
    )

    agent = Agent(
        model=model,
        tools=tools,
        system_prompt=FAST_PROMPT,
        hooks=[
            create_output_steering_handler(),
            create_tool_steering_handler(),
        ],
    )

Benefits of steering over monolithic prompts:
- Reduces prompt bloat (agent ignores instructions buried in 30+ page prompts)
- Contextual guidance at the right moment (before tool calls, before output)
- Enables focused feedback without polluting main context
"""

from __future__ import annotations

from .sop import (
    STEERING_ANTI_PATTERNS,
    STEERING_CONCISENESS,
    STEERING_SIZE_LIMITS,
    STEERING_TOOL_EFFICIENCY,
)

# Steering is experimental in strands
try:
    from strands.experimental.steering import LLMSteeringHandler

    STEERING_AVAILABLE = True
except ImportError:
    STEERING_AVAILABLE = False
    LLMSteeringHandler = None  # type: ignore


def create_output_steering_handler() -> "LLMSteeringHandler":
    """Create a steering handler for output quality control.

    This handler evaluates outputs before they're finalized, checking for:
    - Size limit violations
    - Conciseness issues
    - Anti-pattern violations

    Returns:
        LLMSteeringHandler configured for output quality.

    Raises:
        ImportError: If strands.experimental.steering is not available.
    """
    if not STEERING_AVAILABLE:
        raise ImportError(
            "Steering requires strands.experimental.steering. "
            "Install with: pip install strands-agents[experimental]"
        )

    system_prompt = f"""\
You evaluate agent outputs for quality before finalization.

Your role: Check if the output violates any constraints and provide focused guidance.

{STEERING_SIZE_LIMITS}

{STEERING_CONCISENESS}

{STEERING_ANTI_PATTERNS}

**Decision criteria:**

PROCEED if:
- Output meets size limits
- Uses tables/bullets appropriately
- No filler phrases or redundant descriptions

GUIDE if:
- Size limits exceeded (provide specific reduction suggestions)
- Prose where tables would work better
- Anti-patterns detected (name the specific violation)

Provide brief, actionable feedback. One specific issue at a time."""

    return LLMSteeringHandler(system_prompt=system_prompt)


def create_tool_steering_handler() -> "LLMSteeringHandler":
    """Create a steering handler for tool call optimization.

    This handler evaluates tool calls before execution, checking for:
    - Parallel vs sequential tool usage
    - Output size expectations
    - Tool preference (dedicated tools over shell)

    Returns:
        LLMSteeringHandler configured for tool efficiency.

    Raises:
        ImportError: If strands.experimental.steering is not available.
    """
    if not STEERING_AVAILABLE:
        raise ImportError(
            "Steering requires strands.experimental.steering. "
            "Install with: pip install strands-agents[experimental]"
        )

    system_prompt = f"""\
You evaluate tool calls before execution for efficiency.

Your role: Check if the tool call follows best practices and provide guidance.

{STEERING_TOOL_EFFICIENCY}

**Decision criteria:**

PROCEED if:
- Tool is appropriate for the task
- Sequential dependencies respected
- Output size is within safe limits

GUIDE if:
- Shell command when dedicated tool exists (suggest alternative)
- Missing parallel opportunity (name the tools that could run together)
- Risky command (e.g., `tree` on repo root)

Provide brief, actionable feedback. One specific issue at a time."""

    return LLMSteeringHandler(system_prompt=system_prompt)


def create_all_steering_handlers() -> list:
    """Create all steering handlers for comprehensive guidance.

    Returns:
        List of LLMSteeringHandler instances.

    Raises:
        ImportError: If strands.experimental.steering is not available.
    """
    return [
        create_output_steering_handler(),
        create_tool_steering_handler(),
    ]


__all__ = [
    "STEERING_AVAILABLE",
    "create_output_steering_handler",
    "create_tool_steering_handler",
    "create_all_steering_handlers",
]
