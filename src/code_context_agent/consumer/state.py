"""Mutable display state for agent event rendering.

This module provides Pydantic models for tracking the current state of agent
execution, used by consumers to render live updates.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import ConfigDict, Field

from ..models.base import StrictModel


class SwarmAgentState(StrictModel):
    """State for a single Swarm specialist agent.

    Tracks lifecycle, tool usage, and timing for one agent within a
    multi-agent Swarm run.

    Attributes:
        name: Display name of the specialist agent.
        status: Current lifecycle status ("waiting", "running", "done").
        tool_count: Number of tool calls completed by this agent.
        duration_seconds: Total wall-clock seconds for this agent (set on completion).
        current_tool: Name of the tool currently being executed, if any.
        started_at: Monotonic timestamp when the agent started running.
        findings: Summary strings of notable findings from this agent.
    """

    name: str
    status: str = "waiting"  # "waiting", "running", "done"
    tool_count: int = 0
    duration_seconds: float = 0.0
    current_tool: str | None = None
    started_at: float | None = None
    findings: list[str] = Field(default_factory=list)


class ToolCallState(StrictModel):
    """State for a single tool call.

    Attributes:
        tool_call_id: Unique identifier for the tool call.
        tool_name: Name of the tool being executed.
        agent_name: Name of the swarm agent that invoked this tool.
        args_buffer: Accumulated tool arguments (streaming).
        result: Tool execution result (when complete).
        status: Current status ("running", "completed", "error").
    """

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        extra="forbid",
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
    )

    tool_call_id: str
    tool_name: str
    agent_name: str = ""
    args_buffer: str = ""
    result: Any = None
    status: str = "running"


class AgentDisplayState(StrictModel):
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
        >>> state.active_tool = ToolCallState(tool_call_id="t1", tool_name="rg_search")
    """

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        extra="forbid",
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
    )

    current_phase: str = ""
    text_buffer: str = ""
    active_message_id: str | None = None
    active_tool: ToolCallState | None = None
    completed_tools: list[ToolCallState] = Field(default_factory=list)
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    completed: bool = False
    thread_id: str | None = None
    run_id: str | None = None

    # Metrics for TUI dashboard
    start_time: float | None = None
    max_duration: float = 1200.0
    max_turns: int = 1000
    turn_count: int = 0
    tool_errors: int = 0
    tool_start_time: float | None = None

    # Phase tracking (v7)
    phases: list[Any] = Field(default_factory=list)  # list[PhaseState]
    current_phase_index: int = -1
    discoveries: list[Any] = Field(default_factory=list)  # list[DiscoveryEvent]
    max_discoveries: int = 50

    # Multi-agent tracking (Swarm)
    agents: list[SwarmAgentState] = Field(default_factory=list)
    active_agent_name: str | None = None

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

    def get_tool_stats(self) -> dict[str, int]:
        """Get tool call counts grouped by prefix.

        Groups tools by their name prefix (e.g., lsp_*, code_graph_*) for
        display in the TUI dashboard.

        Returns:
            Dictionary mapping tool prefixes to call counts.
        """
        stats: dict[str, int] = {}
        for tool in self.completed_tools:
            # Group by first part of tool name (before underscore)
            parts = tool.tool_name.split("_")
            prefix = parts[0] + "_*" if len(parts) > 1 else tool.tool_name
            stats[prefix] = stats.get(prefix, 0) + 1
        return stats

    def get_elapsed_seconds(self) -> float:
        """Get elapsed time since run started.

        Returns:
            Elapsed seconds, or 0.0 if not started.
        """
        if self.start_time is None:
            return 0.0
        return time.monotonic() - self.start_time

    def get_tool_elapsed_seconds(self) -> float:
        """Get elapsed time for current tool.

        Returns:
            Elapsed seconds for active tool, or 0.0 if no active tool.
        """
        if self.tool_start_time is None:
            return 0.0
        return time.monotonic() - self.tool_start_time

    def get_success_count(self) -> int:
        """Get count of successful tool calls.

        Returns:
            Number of completed tools minus errors.
        """
        return len(self.completed_tools) - self.tool_errors

    def advance_phase(self, phase: Any) -> None:
        """Advance to a new phase if it's higher than the current one.

        Args:
            phase: AnalysisPhase enum value to advance to.
        """
        from .phases import PHASE_DESCRIPTIONS, PHASE_NAMES, PhaseState

        # Don't regress to a lower phase
        if self.phases and phase <= self.phases[-1].phase:
            return

        # Complete the previous phase
        now = time.monotonic()
        if self.phases and not self.phases[-1].is_complete:
            self.phases[-1].completed_at = now

        # Start the new phase
        self.phases.append(
            PhaseState(
                phase=phase,
                name=PHASE_NAMES.get(phase, f"Phase {phase}"),
                description=PHASE_DESCRIPTIONS.get(phase, ""),
                started_at=now,
            ),
        )
        self.current_phase_index = len(self.phases) - 1

    def add_discovery(self, event: Any) -> None:
        """Add a discovery event, evicting oldest if at capacity.

        Args:
            event: DiscoveryEvent to add.
        """
        self.discoveries.append(event)
        # Capped list — evict oldest when over capacity
        while len(self.discoveries) > self.max_discoveries:
            self.discoveries.pop(0)

    def init_swarm_agents(self, agent_names: list[str]) -> None:
        """Initialize Swarm agent state for tracking.

        Args:
            agent_names: Ordered list of specialist agent names.
        """
        self.agents = [SwarmAgentState(name=name) for name in agent_names]

    def set_active_agent(self, name: str) -> None:
        """Mark an agent as active/running.

        Args:
            name: Name of the agent to activate.
        """
        self.active_agent_name = name
        for agent in self.agents:
            if agent.name == name:
                agent.status = "running"
                agent.started_at = time.monotonic()
                break

    def complete_agent(self, name: str) -> None:
        """Mark an agent as done and record its duration.

        Args:
            name: Name of the agent to complete.
        """
        for agent in self.agents:
            if agent.name == name:
                agent.status = "done"
                if agent.started_at:
                    agent.duration_seconds = time.monotonic() - agent.started_at
                break
        # Clear active if it was this agent
        if self.active_agent_name == name:
            self.active_agent_name = None

    def increment_agent_tool_count(self, agent_name: str | None = None) -> None:
        """Increment tool count for the specified or active agent.

        Args:
            agent_name: Agent to increment for. Falls back to active_agent_name.
        """
        name = agent_name or self.active_agent_name
        if name:
            for agent in self.agents:
                if agent.name == name:
                    agent.tool_count += 1
                    break

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
        # Reset metrics
        self.start_time = None
        self.turn_count = 0
        self.tool_errors = 0
        self.tool_start_time = None
        # Reset phase tracking (v7)
        self.phases = []
        self.current_phase_index = -1
        self.discoveries = []
        # Reset multi-agent tracking (Swarm)
        self.agents = []
        self.active_agent_name = None
