"""Mutable display state for agent event rendering.

This module provides a dataclass for tracking the current state of agent
execution, used by consumers to render live updates.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallState:
    """State for a single tool call.

    Attributes:
        tool_call_id: Unique identifier for the tool call.
        tool_name: Name of the tool being executed.
        args_buffer: Accumulated tool arguments (streaming).
        result: Tool execution result (when complete).
        status: Current status ("running", "completed", "error").
    """

    tool_call_id: str
    tool_name: str
    args_buffer: str = ""
    result: Any = None
    status: str = "running"


@dataclass
class AgentDisplayState:
    """Mutable state for agent display rendering.

    This class tracks all state needed to render the agent's progress
    in a terminal or UI. It accumulates streaming text, tracks active
    and completed tool calls, and maintains error state.

    Attributes:
        current_phase: Description of current analysis phase.
        text_buffer: Accumulated streaming text from agent.
        active_message_id: ID of currently streaming message.
        active_tool: Currently executing tool state (if any).
        completed_tools: List of completed tool executions.
        state_snapshot: Latest state snapshot from agent.
        error: Error message if run failed.
        completed: Whether the run has finished.
        thread_id: Current thread identifier.
        run_id: Current run identifier.

    Example:
        >>> state = AgentDisplayState()
        >>> state.text_buffer += "Analyzing repository..."
        >>> state.active_tool = ToolCallState("t1", "rg_search")
    """

    current_phase: str = ""
    text_buffer: str = ""
    active_message_id: str | None = None
    active_tool: ToolCallState | None = None
    completed_tools: list[ToolCallState] = field(default_factory=list)
    state_snapshot: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    completed: bool = False
    thread_id: str | None = None
    run_id: str | None = None

    def clear_text_buffer(self) -> str:
        """Clear and return the text buffer.

        Returns:
            The text buffer contents before clearing.
        """
        text = self.text_buffer
        self.text_buffer = ""
        return text

    def complete_active_tool(self, result: Any = None) -> None:
        """Mark the active tool as completed and move to history.

        Args:
            result: Optional result to store with the tool call.
        """
        if self.active_tool:
            self.active_tool.status = "completed"
            self.active_tool.result = result
            self.completed_tools.append(self.active_tool)
            self.active_tool = None

    def get_recent_tools(self, count: int = 5) -> list[ToolCallState]:
        """Get the most recent completed tools.

        Args:
            count: Maximum number of tools to return.

        Returns:
            List of recently completed tool states.
        """
        return self.completed_tools[-count:]

    def reset(self) -> None:
        """Reset state for a new run."""
        self.current_phase = ""
        self.text_buffer = ""
        self.active_message_id = None
        self.active_tool = None
        self.completed_tools = []
        self.state_snapshot = {}
        self.error = None
        self.completed = False
