"""Hook providers for agent guidance and quality control.

This module provides HookProvider implementations that integrate with
the Strands hook system for contextual guidance during agent execution.

Uses stable strands.agent.hooks API (not experimental steering).
"""

from __future__ import annotations

from typing import Any, ClassVar

from loguru import logger
from strands.hooks import (
    AfterToolCallEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

_MAX_OUTPUT_SIZE = 100_000


class OutputQualityHook(HookProvider):
    """Hook for output quality enforcement.

    Checks tool results for size limit violations and logs warnings
    when outputs are unusually large.
    """

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register output quality callbacks."""
        registry.add_callback(AfterToolCallEvent, self._check_output_quality)

    def _check_output_quality(self, event: AfterToolCallEvent, **kwargs: Any) -> None:
        """Check tool results for quality issues after execution."""
        tool_name = event.tool_use.get("name", "")
        result_str = str(event.result) if event.result else ""

        if len(result_str) > _MAX_OUTPUT_SIZE:
            logger.warning(f"Tool {tool_name} produced oversized output: {len(result_str)} chars")


class ToolEfficiencyHook(HookProvider):
    """Hook for tool usage optimization.

    Warns when shell is used for tasks that have dedicated tools.
    """

    _SHELL_ALTERNATIVES: ClassVar[dict[str, str]] = {
        "grep": "rg_search",
        "rg ": "rg_search",
        "cat ": "read_file_bounded",
        "tree ": "create_file_manifest (never run tree on repo root)",
        "find ": "create_file_manifest or rg_search",
    }

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register tool efficiency callbacks."""
        registry.add_callback(BeforeToolCallEvent, self._check_tool_efficiency)

    def _check_tool_efficiency(self, event: BeforeToolCallEvent, **kwargs: Any) -> None:
        """Check tool calls for efficiency issues."""
        tool_name = event.tool_use.get("name", "")

        if tool_name == "shell":
            args = event.tool_use.get("input", {})
            command = args.get("command", "")
            if isinstance(command, str):
                for pattern, alternative in self._SHELL_ALTERNATIVES.items():
                    if pattern in command:
                        logger.info(f"Shell command '{command[:50]}' could use {alternative} instead")
                        break


def create_all_hooks() -> list[HookProvider]:
    """Create all hook providers for agent guidance.

    Returns:
        List of HookProvider instances.
    """
    return [
        OutputQualityHook(),
        ToolEfficiencyHook(),
    ]
