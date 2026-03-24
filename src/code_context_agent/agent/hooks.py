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

# Reasoning prompts injected after key analysis tools to force LLM interpretation
_REASONING_PROMPTS: dict[str, str] = {
    "code_graph_analyze": (
        "[REASONING CHECKPOINT] Before calling the next tool, interpret these graph results. "
        "What structural pattern do they reveal? Which files appear as bottlenecks or foundations? "
        "How does this change your understanding of the architecture?"
    ),
    "code_graph_explore": (
        "[REASONING CHECKPOINT] What does this exploration reveal about the code structure? "
        "Are there unexpected clusters, isolated components, or surprising dependency directions?"
    ),
    "git_hotspots": (
        "[REASONING CHECKPOINT] Which high-churn files overlap with structurally central files from graph analysis? "
        "High churn + high centrality = fragile bottleneck. Note any files that are hot but structurally peripheral "
        "(may indicate config thrash or generated code)."
    ),
    "git_files_changed_together": (
        "[REASONING CHECKPOINT] Do these co-change patterns match the static dependency graph? "
        "Files that change together WITHOUT a static dependency edge indicate an implicit coupling "
        "that an AI coding assistant must know about."
    ),
    "git_blame_summary": (
        "[REASONING CHECKPOINT] What does the ownership distribution reveal? "
        "Single-author files with high centrality = bus factor risk. "
        "Many-author files with complex logic = coordination risk."
    ),
    "read_file_bounded": (
        "[REASONING CHECKPOINT] Now that you have read this code, compare what you see against "
        "what the graph metrics predicted. Does the code complexity match its structural importance? "
        "What domain invariants does this file maintain? What would break if it were changed naively?"
    ),
}


class FullModeToolError(RuntimeError):
    """Raised by FailFastHook when a critical tool returns an error in full mode."""

    def __init__(self, tool_name: str, error_message: str) -> None:  # noqa: D107
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' failed: {error_message}")


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


class ReasoningCheckpointHook(HookProvider):
    """Hook that enriches key tool results with reasoning prompts.

    After analysis tools return results, appends a reasoning checkpoint
    that asks the model to interpret the data before proceeding. This
    forces the LLM to reason over combined signals rather than just
    collecting tool outputs.
    """

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register reasoning checkpoint callback."""
        registry.add_callback(AfterToolCallEvent, self._inject_reasoning_prompt)

    def _inject_reasoning_prompt(self, event: AfterToolCallEvent, **kwargs: Any) -> None:
        """Append reasoning prompt to tool results for key analysis tools."""
        tool_name = event.tool_use.get("name", "")

        prompt = _REASONING_PROMPTS.get(tool_name)
        if not prompt:
            return

        result = event.result
        if not result or result.get("status") == "error":
            return

        content = result.get("content", [])
        if not content:
            return

        # Append reasoning checkpoint as additional text content
        content.append({"text": f"\n\n{prompt}"})
        logger.debug(f"Reasoning checkpoint injected for {tool_name}")


class FailFastHook(HookProvider):
    """Hook that raises on tool errors in --full mode.

    In full mode, most tool failures should halt analysis immediately
    rather than silently degrading. Exempt tools (search, shutdown, MCP)
    are allowed to fail without halting.
    """

    EXEMPT_TOOLS: ClassVar[frozenset[str]] = frozenset(
        {
            # Search tools may legitimately return no results
            "rg_search",
            "lsp_workspace_symbols",
            # Shutdown is best-effort
            "lsp_shutdown",
            # Graph load may fail if no prior graph exists
            "code_graph_load",
            # MCP tools are external and may be unavailable
            "context7_resolve-library-id",
            "context7_query-docs",
            # Shell is user-controlled
            "shell",
        },
    )

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register fail-fast callback."""
        registry.add_callback(AfterToolCallEvent, self._check_for_error)

    def _check_for_error(self, event: AfterToolCallEvent, **kwargs: Any) -> None:
        """Raise FullModeToolError if a non-exempt tool returned an error."""
        import json as _json

        tool_name = event.tool_use.get("name", "")

        if tool_name in self.EXEMPT_TOOLS:
            return

        result_str = str(event.result) if event.result else ""
        if not result_str:
            return

        try:
            data = _json.loads(result_str)
        except (_json.JSONDecodeError, TypeError):
            return

        if isinstance(data, dict) and data.get("status") == "error":
            error_msg = data.get("error", data.get("message", "unknown error"))
            raise FullModeToolError(tool_name, str(error_msg))


def create_all_hooks(*, full_mode: bool = False) -> list[HookProvider]:
    """Create all hook providers for agent guidance.

    Args:
        full_mode: If True, include FailFastHook for strict error handling.

    Returns:
        List of HookProvider instances.
    """
    hooks: list[HookProvider] = [
        OutputQualityHook(),
        ToolEfficiencyHook(),
        ReasoningCheckpointHook(),
    ]
    if full_mode:
        hooks.append(FailFastHook())
    return hooks
