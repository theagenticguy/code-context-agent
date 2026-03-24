"""Hook providers for agent guidance and quality control.

This module provides HookProvider implementations that integrate with
the Strands hook system for contextual guidance during agent execution.

Uses stable strands.agent.hooks API (not experimental steering).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ..consumer.state import AgentDisplayState

from loguru import logger
from strands.hooks import (
    AfterToolCallEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)
from strands.hooks.events import (
    AfterNodeCallEvent,
    BeforeNodeCallEvent,
)

_MAX_OUTPUT_SIZE = 100_000


def _is_error_result(result: Any) -> bool:
    """Check if a tool result indicates an error."""
    if not result:
        return False
    result_str = str(result)
    return '"status": "error"' in result_str or '"status":"error"' in result_str


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

    Truncates oversized tool results to prevent context window overflow,
    and logs warnings when outputs are unusually large.
    """

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register output quality callbacks."""
        registry.add_callback(AfterToolCallEvent, self._check_output_quality)

    def _check_output_quality(self, event: AfterToolCallEvent, **kwargs: Any) -> None:
        """Truncate oversized tool results to prevent context window overflow."""
        tool_name = event.tool_use.get("name", "")
        result = event.result
        if not result:
            return

        content = result.get("content", [])
        if not content:
            return

        # Measure total text size across all content blocks
        total_size = sum(len(block.get("text", "")) for block in content if isinstance(block, dict))

        if total_size > _MAX_OUTPUT_SIZE:
            logger.warning(
                f"Tool {tool_name} produced oversized output: {total_size} chars, truncating to {_MAX_OUTPUT_SIZE}",
            )
            # Truncate text blocks to fit within the limit
            truncated = False
            new_content = []
            remaining = _MAX_OUTPUT_SIZE
            for block in content:
                if not isinstance(block, dict) or "text" not in block:
                    new_content.append(block)
                    continue
                text = block["text"]
                if remaining <= 0:
                    continue
                if len(text) > remaining:
                    block["text"] = (
                        text[:remaining] + f"\n\n[TRUNCATED: output was {total_size} chars, "
                        f"showing first {_MAX_OUTPUT_SIZE}. Use smaller top_k.]"
                    )
                    truncated = True
                remaining -= len(text)
                new_content.append(block)
            if truncated:
                result["content"] = new_content


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


class SwarmDisplayHook(HookProvider):
    """Hook that tracks Swarm node transitions for multi-agent TUI display.

    Updates AgentDisplayState when agents start/stop, enabling the Rich
    dashboard to show which specialist is currently active.
    """

    def __init__(self, state: AgentDisplayState) -> None:  # noqa: D107
        self._state = state

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register Swarm node transition callbacks."""
        registry.add_callback(BeforeNodeCallEvent, self._on_node_start)
        registry.add_callback(AfterNodeCallEvent, self._on_node_end)

    def _on_node_start(self, event: BeforeNodeCallEvent, **kwargs: Any) -> None:
        """Update state when a Swarm agent starts."""
        logger.info(f"Swarm agent started: {event.node_id}")
        self._state.set_active_agent(event.node_id)

    def _on_node_end(self, event: AfterNodeCallEvent, **kwargs: Any) -> None:
        """Update state when a Swarm agent completes."""
        logger.info(f"Swarm agent completed: {event.node_id}")
        self._state.complete_agent(event.node_id)


class ToolDisplayHook(HookProvider):
    """Hook that tracks tool calls for TUI display.

    Updates AgentDisplayState with active tool information and extracts
    discovery events from tool results (file counts, symbols, etc.).
    """

    def __init__(self, state: AgentDisplayState) -> None:  # noqa: D107
        self._state = state

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register tool call display callbacks."""
        registry.add_callback(BeforeToolCallEvent, self._on_tool_start)
        registry.add_callback(AfterToolCallEvent, self._on_tool_end)

    def _on_tool_start(self, event: BeforeToolCallEvent, **kwargs: Any) -> None:
        """Update state when a tool call begins."""
        import time

        from ..consumer.state import ToolCallState

        tool_name = event.tool_use.get("name", "")
        tool_id = event.tool_use.get("toolUseId", "")
        if tool_name:
            self._state.active_tool = ToolCallState(
                tool_call_id=tool_id,
                tool_name=tool_name,
                args_buffer="",
                result=None,
                status="running",
            )
            self._state.tool_start_time = time.monotonic()

    def _on_tool_end(self, event: AfterToolCallEvent, **kwargs: Any) -> None:
        """Update state when a tool call completes."""
        tool_name = event.tool_use.get("name", "")
        if not tool_name:
            return

        is_error = _is_error_result(event.result)

        if self._state.active_tool:
            self._state.active_tool.status = "error" if is_error else "completed"
            self._state.active_tool.result = str(event.result)[:200] if event.result else ""
            self._state.completed_tools.append(self._state.active_tool)
            self._state.active_tool = None
            if is_error:
                self._state.tool_errors += 1


class JsonLogHook(HookProvider):
    """Hook that emits structured JSON log lines for CI/CD --quiet mode.

    Outputs one JSON line per significant event (tool start/end).
    Uses loguru's serialize mode for consistent formatting.
    """

    def __init__(self) -> None:  # noqa: D107
        self._json_logger = logger.bind(output="json")

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register JSON log callbacks for tool events."""
        registry.add_callback(BeforeToolCallEvent, self._on_tool_start)
        registry.add_callback(AfterToolCallEvent, self._on_tool_end)

    def _on_tool_start(self, event: BeforeToolCallEvent, **kwargs: Any) -> None:
        """Emit JSON log line when a tool call begins."""
        tool_name = event.tool_use.get("name", "")
        if tool_name:
            self._json_logger.info("tool_start", tool=tool_name)

    def _on_tool_end(self, event: AfterToolCallEvent, **kwargs: Any) -> None:
        """Emit JSON log line when a tool call completes."""
        tool_name = event.tool_use.get("name", "")
        is_error = _is_error_result(event.result)
        if tool_name:
            self._json_logger.info(
                "tool_end",
                tool=tool_name,
                status="error" if is_error else "ok",
            )


class JsonLogSwarmHook(HookProvider):
    """Hook that emits JSON log lines for Swarm agent transitions."""

    def __init__(self) -> None:  # noqa: D107
        self._json_logger = logger.bind(output="json")

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register JSON log callbacks for Swarm node events."""
        registry.add_callback(BeforeNodeCallEvent, self._on_node_start)
        registry.add_callback(AfterNodeCallEvent, self._on_node_end)

    def _on_node_start(self, event: BeforeNodeCallEvent, **kwargs: Any) -> None:
        """Emit JSON log line when a Swarm agent starts."""
        self._json_logger.info("agent_start", agent=event.node_id)

    def _on_node_end(self, event: AfterNodeCallEvent, **kwargs: Any) -> None:
        """Emit JSON log line when a Swarm agent completes."""
        self._json_logger.info("agent_end", agent=event.node_id)


def create_all_hooks(
    *,
    full_mode: bool = False,
    state: Any | None = None,
    quiet: bool = False,
) -> tuple[list[HookProvider], list[HookProvider]]:
    """Create all hook providers for agent guidance and display.

    Returns a tuple of (agent_hooks, swarm_hooks).
    Agent hooks are registered on each Agent node.
    Swarm hooks are registered on the Swarm itself.

    Args:
        full_mode: If True, include FailFastHook.
        state: AgentDisplayState for TUI display. None if quiet mode.
        quiet: If True, use JsonLogHook instead of display hooks.

    Returns:
        Tuple of (agent_hooks, swarm_hooks).
    """
    # Agent-level hooks (registered on each Agent node)
    agent_hooks: list[HookProvider] = [
        OutputQualityHook(),
        ToolEfficiencyHook(),
        ReasoningCheckpointHook(),
    ]
    if full_mode:
        agent_hooks.append(FailFastHook())

    # Display hooks
    if quiet:
        agent_hooks.append(JsonLogHook())
    elif state is not None:
        agent_hooks.append(ToolDisplayHook(state))

    # Swarm-level hooks (registered on the Swarm)
    swarm_hooks: list[HookProvider] = []
    if quiet:
        swarm_hooks.append(JsonLogSwarmHook())
    elif state is not None:
        swarm_hooks.append(SwarmDisplayHook(state))

    return agent_hooks, swarm_hooks
