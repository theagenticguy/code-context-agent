"""Rich terminal display consumer for agent events.

This module provides a Rich-based event consumer that renders agent
progress in a terminal with live updates, spinners, and formatted output.
"""

import time
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
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

    def _format_time(self, seconds: float) -> str:
        """Format seconds as MM:SS string."""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def _build_progress_bar(self, completed: float, total: float, width: int = 40) -> str:
        """Build a text-based progress bar.

        Args:
            completed: Current progress value.
            total: Maximum progress value.
            width: Character width of the bar.

        Returns:
            Progress bar string like "━━━━━━━━━━░░░░░░░░░░  50%"
        """
        if total <= 0:
            return "░" * width + "   0%"
        ratio = min(completed / total, 1.0)
        filled = int(width * ratio)
        empty = width - filled
        percent = int(ratio * 100)
        return "━" * filled + "░" * empty + f"  {percent:3d}%"

    def _build_mini_bar(self, count: int, max_count: int, width: int = 10) -> str:
        """Build a mini progress bar for tool stats.

        Args:
            count: Current count.
            max_count: Maximum count (for scaling).
            width: Character width of the bar.

        Returns:
            Mini bar string like "████████░░"
        """
        if max_count <= 0:
            return "░" * width
        ratio = min(count / max_count, 1.0)
        filled = int(width * ratio)
        empty = width - filled
        return "█" * filled + "░" * empty

    def _build_timer_section(self) -> RenderableType:
        """Build the timer and progress section.

        Returns:
            Text renderable with timer info and progress bar.
        """
        elapsed = self.state.get_elapsed_seconds()
        max_dur = self.state.max_duration
        turns = self.state.turn_count
        max_turns = self.state.max_turns

        # Calculate progress based on whichever limit is closer
        time_ratio = elapsed / max_dur if max_dur > 0 else 0
        turn_ratio = turns / max_turns if max_turns > 0 else 0
        progress_ratio = max(time_ratio, turn_ratio)

        lines = Text()
        lines.append("  ⏱  Time: ", style="dim")
        lines.append(self._format_time(elapsed), style="bold cyan")
        lines.append(f" / {self._format_time(max_dur)}", style="dim")
        lines.append("    Turns: ", style="dim")
        lines.append(str(turns), style="bold cyan")
        lines.append(f" / {max_turns}", style="dim")
        lines.append("\n")
        lines.append("  " + self._build_progress_bar(progress_ratio, 1.0), style="cyan")

        return lines

    def _build_tool_stats_section(self) -> RenderableType:
        """Build the tool statistics section.

        Returns:
            Text renderable with tool stats and category breakdown.
        """
        total = len(self.state.completed_tools)
        if self.state.active_tool:
            total += 1
        success = self.state.get_success_count()
        errors = self.state.tool_errors

        lines = Text()
        lines.append("  Tools: ", style="dim")
        lines.append(str(total), style="bold")
        lines.append(" total   ", style="dim")
        lines.append("✓ ", style="green")
        lines.append(str(success), style="bold green")
        lines.append(" success   ", style="dim")
        lines.append("✗ ", style="red")
        lines.append(str(errors), style="bold red")
        lines.append(" errors", style="dim")

        # Tool breakdown by category
        stats = self.state.get_tool_stats()
        if stats:
            max_count = max(stats.values()) if stats else 1
            lines.append("\n")
            sorted_stats = sorted(stats.items(), key=lambda x: -x[1])
            for i, (prefix, count) in enumerate(sorted_stats[:5]):  # Top 5 categories
                connector = "└──" if i == len(sorted_stats[:5]) - 1 else "├──"
                lines.append(f"\n  {connector} ", style="dim")
                lines.append(f"{prefix:<15}", style="cyan")
                lines.append(f"{count:>3} calls   ", style="dim")
                lines.append(self._build_mini_bar(count, max_count), style="green")

        return lines

    def _build_active_tool_section(self) -> RenderableType | None:
        """Build the active tool indicator section.

        Returns:
            Spinner with tool info, or None if no active tool.
        """
        if not self.state.active_tool:
            return None

        tool_elapsed = self.state.get_tool_elapsed_seconds()
        return Spinner(
            "dots",
            text=Text.assemble(
                ("  Running: ", "dim"),
                (self.state.active_tool.tool_name, "bold yellow"),
                (f" ({tool_elapsed:.1f}s)", "dim"),
            ),
        )

    def _build_display(self) -> RenderableType:
        """Build the current display from state.

        Returns:
            Rich renderable representing current agent state.
        """
        inner_elements: list[RenderableType] = []

        # Header with phase info
        if self.state.current_phase:
            header = Text()
            header.append("Phase: ", style="dim")
            header.append(self.state.current_phase, style="bold blue")
            inner_elements.append(header)
            inner_elements.append(Text(""))  # Spacer

        # Timer and progress section
        inner_elements.append(self._build_timer_section())
        inner_elements.append(Text(""))  # Spacer

        # Tool statistics section
        inner_elements.append(self._build_tool_stats_section())

        # Active tool indicator
        active_tool = self._build_active_tool_section()
        if active_tool:
            inner_elements.append(Text(""))  # Spacer
            inner_elements.append(active_tool)

        # Streaming text buffer (truncated for display)
        if self.state.text_buffer:
            inner_elements.append(Text(""))  # Spacer
            # Show last MAX_DISPLAY_BUFFER_SIZE chars to avoid display overflow
            text_content = self.state.text_buffer[-MAX_DISPLAY_BUFFER_SIZE:]
            if len(self.state.text_buffer) > MAX_DISPLAY_BUFFER_SIZE:
                text_content = "..." + text_content

            inner_elements.append(
                Panel(
                    Markdown(text_content),
                    title="Agent Reasoning",
                    border_style="green",
                    padding=(0, 1),
                )
            )

        # Error display
        if self.state.error:
            inner_elements.append(
                Panel(
                    Text(self.state.error, style="bold red"),
                    title="Error",
                    border_style="red",
                )
            )

        # Completion indicator
        if self.state.completed:
            inner_elements.append(Text(""))  # Spacer
            inner_elements.append(Text("  ✓ Analysis complete!", style="bold green"))

        # Wrap everything in a main panel
        run_title = f"Run: {self.state.run_id[:8]}" if self.state.run_id else "Agent"
        return Panel(
            Group(*inner_elements) if inner_elements else Text("Starting analysis...", style="dim"),
            title=run_title,
            border_style="cyan",
            padding=(1, 2),
        )

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
        self.state.start_time = time.monotonic()
        self._refresh()

    async def on_text_start(self, message_id: str, role: str) -> None:
        """Handle start of text message.

        Args:
            message_id: Message identifier.
            role: Message role.
        """
        self.state.active_message_id = message_id
        self.state.text_buffer = ""  # Clear buffer for new message
        self._refresh()

    async def on_text_content(self, message_id: str, delta: str) -> None:
        """Handle streaming text content.

        Args:
            message_id: Message identifier.
            delta: New text chunk.
        """
        # Normalize newlines for consistent markdown display
        normalized = delta.replace("\r\n", "\n").replace("\r", "\n")
        self.state.text_buffer += normalized
        self._refresh()

    async def on_text_end(self, message_id: str) -> None:
        """Handle end of text message.

        Args:
            message_id: Message identifier.
        """
        self.state.active_message_id = None
        self.state.turn_count += 1
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
        self.state.tool_start_time = time.monotonic()
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
            # Check for error in result
            if isinstance(result, str) and "error" in result.lower():
                self.state.tool_errors += 1
            elif isinstance(result, dict) and result.get("error"):
                self.state.tool_errors += 1
        self._refresh()

    async def on_tool_end(self, tool_call_id: str) -> None:
        """Handle end of tool execution.

        Args:
            tool_call_id: Tool call identifier.
        """
        if self.state.active_tool and self.state.active_tool.tool_call_id == tool_call_id:
            self.state.complete_active_tool()
        # Add visual separator after tool completes for cleaner display
        if self.state.text_buffer and not self.state.text_buffer.endswith("\n\n"):
            self.state.text_buffer += "\n\n"
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
