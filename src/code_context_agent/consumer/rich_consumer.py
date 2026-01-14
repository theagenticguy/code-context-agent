"""Rich terminal display consumer for agent events.

This module provides a Rich-based event consumer that renders agent
progress in a terminal with live updates, spinners, and formatted output.
"""

from typing import Any

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .base import EventConsumer
from .state import AgentDisplayState, ToolCallState

# Maximum characters to display in the text buffer to avoid terminal overflow
MAX_DISPLAY_BUFFER_SIZE = 2000


class RichEventConsumer(EventConsumer):
    """Rich terminal display consumer for agent streaming events.

    Uses Rich's Live display to show real-time updates as the agent
    executes, including streaming text, tool execution status, and
    progress indicators.

    Attributes:
        console: Rich Console instance for output.
        state: Current display state tracking.

    Example:
        >>> consumer = RichEventConsumer()
        >>> await consumer.start()
        >>> await consumer.on_run_started("thread-1", "run-1")
        >>> await consumer.on_text_content("msg-1", "Analyzing...")
        >>> await consumer.stop()
    """

    def __init__(self, console: Console | None = None) -> None:
        """Initialize the Rich event consumer.

        Args:
            console: Optional Rich Console instance. Creates new if not provided.
        """
        self.console = console or Console()
        self.state = AgentDisplayState()
        self._live: Live | None = None

    def _build_display(self) -> RenderableType:
        """Build the current display from state.

        Returns:
            Rich renderable representing current agent state.
        """
        elements: list[RenderableType] = []

        # Header with run info
        if self.state.run_id:
            header = Text()
            header.append("Run: ", style="dim")
            header.append(self.state.run_id[:8], style="cyan")
            if self.state.current_phase:
                header.append(" | Phase: ", style="dim")
                header.append(self.state.current_phase, style="bold blue")
            elements.append(header)

        # Active tool indicator with spinner
        if self.state.active_tool:
            tool_display = Spinner(
                "dots",
                text=Text.assemble(
                    ("Running: ", "dim"),
                    (self.state.active_tool.tool_name, "bold yellow"),
                ),
            )
            elements.append(tool_display)

        # Streaming text buffer (truncated for display)
        if self.state.text_buffer:
            # Show last MAX_DISPLAY_BUFFER_SIZE chars to avoid display overflow
            text_content = self.state.text_buffer[-MAX_DISPLAY_BUFFER_SIZE:]
            if len(self.state.text_buffer) > MAX_DISPLAY_BUFFER_SIZE:
                text_content = "..." + text_content

            elements.append(
                Panel(
                    Markdown(text_content),
                    title="Agent Reasoning",
                    border_style="green",
                    padding=(0, 1),
                )
            )

        # Recent tool results table
        recent_tools = self.state.get_recent_tools(5)
        if recent_tools:
            table = Table(title="Recent Tools", show_lines=False, expand=False)
            table.add_column("Tool", style="cyan", no_wrap=True)
            table.add_column("Status", style="green", no_wrap=True)

            for tool in recent_tools:
                status_style = "green" if tool.status == "completed" else "yellow"
                table.add_row(
                    tool.tool_name,
                    Text(tool.status, style=status_style),
                )
            elements.append(table)

        # Error display
        if self.state.error:
            elements.append(
                Panel(
                    Text(self.state.error, style="bold red"),
                    title="Error",
                    border_style="red",
                )
            )

        # Completion indicator
        if self.state.completed:
            elements.append(Text("Analysis complete!", style="bold green"))

        return Group(*elements) if elements else Text("Starting analysis...", style="dim")

    def _refresh(self) -> None:
        """Refresh the live display with current state."""
        if self._live:
            self._live.update(self._build_display())

    async def start(self) -> None:
        """Start the Rich Live display."""
        self.state.reset()
        self._live = Live(
            self._build_display(),
            console=self.console,
            refresh_per_second=4,
            transient=False,
        )
        self._live.start()

    async def stop(self) -> None:
        """Stop the Rich Live display."""
        if self._live:
            self._live.stop()
            self._live = None

    async def on_run_started(self, thread_id: str, run_id: str) -> None:
        """Handle run started event.

        Args:
            thread_id: Thread identifier.
            run_id: Run identifier.
        """
        self.state.thread_id = thread_id
        self.state.run_id = run_id
        self._refresh()

    async def on_text_start(self, message_id: str, role: str) -> None:
        """Handle start of text message.

        Args:
            message_id: Message identifier.
            role: Message role.
        """
        self.state.active_message_id = message_id
        self._refresh()

    async def on_text_content(self, message_id: str, delta: str) -> None:
        """Handle streaming text content.

        Args:
            message_id: Message identifier.
            delta: New text chunk.
        """
        self.state.text_buffer += delta
        self._refresh()

    async def on_text_end(self, message_id: str) -> None:
        """Handle end of text message.

        Args:
            message_id: Message identifier.
        """
        self.state.active_message_id = None
        self._refresh()

    async def on_tool_start(self, tool_call_id: str, tool_name: str) -> None:
        """Handle start of tool execution.

        Args:
            tool_call_id: Tool call identifier.
            tool_name: Name of tool being called.
        """
        self.state.active_tool = ToolCallState(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )
        self._refresh()

    async def on_tool_args(self, tool_call_id: str, args_delta: str) -> None:
        """Handle streaming tool arguments.

        Args:
            tool_call_id: Tool call identifier.
            args_delta: Arguments JSON chunk.
        """
        if self.state.active_tool and self.state.active_tool.tool_call_id == tool_call_id:
            self.state.active_tool.args_buffer += args_delta
        self._refresh()

    async def on_tool_result(self, tool_call_id: str, result: Any) -> None:
        """Handle tool result.

        Args:
            tool_call_id: Tool call identifier.
            result: Tool result.
        """
        if self.state.active_tool and self.state.active_tool.tool_call_id == tool_call_id:
            self.state.active_tool.result = result
        self._refresh()

    async def on_tool_end(self, tool_call_id: str) -> None:
        """Handle end of tool execution.

        Args:
            tool_call_id: Tool call identifier.
        """
        if self.state.active_tool and self.state.active_tool.tool_call_id == tool_call_id:
            self.state.complete_active_tool()
        self._refresh()

    async def on_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Handle state snapshot.

        Args:
            snapshot: State snapshot dictionary.
        """
        self.state.state_snapshot = snapshot
        # Extract phase from snapshot if available
        if "phase" in snapshot:
            self.state.current_phase = str(snapshot["phase"])
        self._refresh()

    async def on_run_finished(self, thread_id: str, run_id: str) -> None:
        """Handle run finished.

        Args:
            thread_id: Thread identifier.
            run_id: Run identifier.
        """
        self.state.completed = True
        self._refresh()

    async def on_error(self, message: str, code: str | None = None) -> None:
        """Handle error.

        Args:
            message: Error message.
            code: Optional error code.
        """
        error_text = message
        if code:
            error_text = f"[{code}] {message}"
        self.state.error = error_text
        self._refresh()


class QuietConsumer(EventConsumer):
    """Minimal consumer that only prints final result.

    Use this when --quiet flag is passed to suppress live output.
    """

    def __init__(self, console: Console | None = None) -> None:
        """Initialize quiet consumer.

        Args:
            console: Optional Rich Console for final output.
        """
        self.console = console or Console()
        self._error: str | None = None

    async def on_run_started(self, thread_id: str, run_id: str) -> None:
        """Handle run started - no output."""

    async def on_text_start(self, message_id: str, role: str) -> None:
        """Handle text start - no output."""

    async def on_text_content(self, message_id: str, delta: str) -> None:
        """Handle text content - no output."""

    async def on_text_end(self, message_id: str) -> None:
        """Handle text end - no output."""

    async def on_tool_start(self, tool_call_id: str, tool_name: str) -> None:
        """Handle tool start - no output."""

    async def on_tool_args(self, tool_call_id: str, args_delta: str) -> None:
        """Handle tool args - no output."""

    async def on_tool_result(self, tool_call_id: str, result: Any) -> None:
        """Handle tool result - no output."""

    async def on_tool_end(self, tool_call_id: str) -> None:
        """Handle tool end - no output."""

    async def on_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Handle state snapshot - no output."""

    async def on_run_finished(self, thread_id: str, run_id: str) -> None:
        """Handle run finished - print success."""
        if not self._error:
            self.console.print("[green]Analysis complete![/green]")

    async def on_error(self, message: str, code: str | None = None) -> None:
        """Handle error - print error message."""
        self._error = message
        error_text = f"[{code}] {message}" if code else message
        self.console.print(f"[bold red]Error:[/bold red] {error_text}")
