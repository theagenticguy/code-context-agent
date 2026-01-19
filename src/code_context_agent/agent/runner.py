"""Agent runner with event streaming and display.

This module provides functions to run the analysis agent and stream
events to consumers for display or further processing.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Callable

from ag_ui.core import EventType, RunAgentInput, UserMessage
from ag_ui_strands import StrandsAgent
from loguru import logger
from pydantic import BaseModel

from ..config import get_settings
from ..consumer import EventConsumer, QuietConsumer, RichEventConsumer
from .factory import create_agent

# Disable shell tool approval prompts and console output - we're running non-interactively
os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")
os.environ.setdefault("STRANDS_NON_INTERACTIVE", "true")

# Monkey-patch StrandsAgent to preserve callback_handler from original agent
# This prevents duplicate output from PrintingCallbackHandler
_original_strands_agent_init = StrandsAgent.__init__


def _patched_strands_agent_init(self, agent, name, description="", config=None):
    """Patched init that captures callback_handler from the original agent."""
    _original_strands_agent_init(self, agent, name, description, config)
    # Add callback_handler to _agent_kwargs so per-thread agents inherit it
    self._agent_kwargs["callback_handler"] = getattr(agent, "callback_handler", None)


StrandsAgent.__init__ = _patched_strands_agent_init

# Default execution bounds (can be overridden by config)
DEFAULT_MAX_TURNS = 1000
DEFAULT_MAX_DURATION = 600  # 10 minutes (FAST mode)
DEFAULT_DEEP_MAX_DURATION = 1200  # 20 minutes (DEEP mode)


class AnalysisContext(BaseModel):
    """Container for analysis components and configuration."""

    repo: Path
    output: Path
    mode: str
    agui_agent: Any  # StrandsAgent instance
    consumer: EventConsumer
    max_turns: int
    max_duration: int


class StreamResult(BaseModel):
    """Result of streaming analysis execution."""

    status: str  # "completed", "error", "stopped"
    turn_count: int
    duration_seconds: float
    error_message: str | None = None
    exceeded_limit: str | None = None


def _build_analysis_prompt(repo: Path, output: Path, mode: str, focus: str | None) -> str:
    """Build the analysis prompt with optional focus area.

    Args:
        repo: Repository path
        output: Output directory path
        mode: Analysis mode (fast/deep)
        focus: Optional focus area

    Returns:
        Formatted prompt string
    """
    focus_instruction = ""
    if focus:
        focus_instruction = f"""
FOCUS AREA: {focus}
Prioritize analysis of code related to this focus area. When selecting files for the bundle
and writing narration, emphasize components, functions, and patterns relevant to: {focus}
"""

    return f"""
Analyze the repository at: {repo}

Output all files to: {output}

Mode: {mode.upper()}
{focus_instruction}
Follow your SOP to produce the narrated context bundle.
Start with Phase 0 (create_file_manifest) and proceed through all phases.
"""


def _get_execution_bounds(mode: str) -> tuple[int, int]:
    """Get execution bounds (max_turns, max_duration) for the given mode.

    Args:
        mode: Analysis mode (fast/deep)

    Returns:
        Tuple of (max_turns, max_duration_seconds)
    """
    settings = get_settings()
    max_turns = getattr(settings, "agent_max_turns", DEFAULT_MAX_TURNS)

    if mode == "deep":
        max_duration = getattr(
            settings,
            "deep_mode_max_duration",
            DEFAULT_DEEP_MAX_DURATION,
        )
    else:
        max_duration = getattr(settings, "agent_max_duration", DEFAULT_MAX_DURATION)

    return max_turns, max_duration


def _setup_analysis_context(
    repo_path: str | Path,
    output_dir: str | Path | None,
    mode: str,
    focus: str | None,
    consumer: EventConsumer | None,
    quiet: bool,
    use_steering: bool,
) -> AnalysisContext:
    """Initialize all analysis components.

    Args:
        repo_path: Path to repository
        output_dir: Optional output directory
        mode: Analysis mode
        focus: Optional focus area
        consumer: Optional event consumer
        quiet: Quiet mode flag
        use_steering: Use steering flag

    Returns:
        AnalysisContext with all components initialized
    """
    repo = Path(repo_path).resolve()
    output = Path(output_dir).resolve() if output_dir else repo / ".agent"

    if not repo.exists():
        raise ValueError(f"Repository path does not exist: {repo}")

    output.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting {mode.upper()} analysis: {repo}")

    # Create consumer if not provided
    if consumer is None:
        consumer = QuietConsumer() if quiet else RichEventConsumer()

    # Create the strands agent
    strands_agent = create_agent(mode=mode, use_steering=use_steering)

    # Wrap with ag-ui-strands for typed event streaming
    agui_agent = StrandsAgent(
        agent=strands_agent,
        name="code_context_agent",
        description=f"Code context analysis agent ({mode} mode)",
    )

    # Get execution bounds
    max_turns, max_duration = _get_execution_bounds(mode)

    return AnalysisContext(
        repo=repo,
        output=output,
        mode=mode,
        agui_agent=agui_agent,
        consumer=consumer,
        max_turns=max_turns,
        max_duration=max_duration,
    )


async def _execute_analysis_stream(
    context: AnalysisContext,
    prompt: str,
) -> StreamResult:
    """Run the agent and process event stream.

    Args:
        context: Analysis context with agent and configuration
        prompt: Analysis prompt

    Returns:
        StreamResult with execution details
    """
    # Build input for ag-ui
    input_data = RunAgentInput(
        thread_id="analysis-thread",
        run_id=f"run-{context.mode}",
        messages=[UserMessage(id="msg-1", role="user", content=prompt)],
        state={},
        tools=[],
        context=[],
        forwarded_props={},
    )

    # Start consumer display and pass limits to state
    await context.consumer.start()
    if hasattr(context.consumer, "state"):
        context.consumer.state.max_turns = context.max_turns
        context.consumer.state.max_duration = context.max_duration

    start_time = time.monotonic()
    turn_count = 0
    exceeded_limit: str | None = None
    error_message: str | None = None

    try:
        # Stream events from ag-ui-strands
        async for event in context.agui_agent.run(input_data):
            elapsed = time.monotonic() - start_time

            # Count actual turns (completed assistant messages)
            if hasattr(event, "type") and event.type == EventType.TEXT_MESSAGE_END:
                turn_count += 1

                # Check turn limit only on actual turns
                if turn_count > context.max_turns:
                    logger.warning(f"Agent exceeded {context.max_turns} turns, stopping")
                    exceeded_limit = f"max_turns ({context.max_turns})"
                    break

            # Check time limit on every event
            if elapsed > context.max_duration:
                logger.warning(
                    f"Agent exceeded {context.max_duration}s duration, stopping",
                )
                exceeded_limit = f"max_duration ({context.max_duration}s)"
                break

            await _dispatch_event(event, context.consumer)

            # Check for error
            if hasattr(event, "type") and event.type == EventType.RUN_ERROR:
                error_message = getattr(event, "message", "Unknown error")
                break

    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        logger.error(f"Analysis error: {e}\n{tb}")
        error_message = str(e) if str(e) else f"{type(e).__name__}: {tb}"
        await context.consumer.on_error(error_message)

    final_duration = time.monotonic() - start_time

    # Determine status
    if error_message:
        status = "error"
    elif exceeded_limit:
        status = "stopped"
    else:
        status = "completed"

    return StreamResult(
        status=status,
        turn_count=turn_count,
        duration_seconds=final_duration,
        error_message=error_message,
        exceeded_limit=exceeded_limit,
    )


async def _cleanup_context(context: AnalysisContext) -> None:
    """Cleanup resources after analysis.

    Args:
        context: Analysis context
    """
    await context.consumer.stop()

    # Cleanup LSP sessions
    from ..tools.lsp.session import get_session_manager

    await get_session_manager().shutdown_all()


async def run_analysis(
    repo_path: str | Path,
    output_dir: str | Path | None = None,
    mode: str = "fast",
    focus: str | None = None,
    consumer: EventConsumer | None = None,
    quiet: bool = False,
    use_steering: bool = True,
) -> dict[str, Any]:
    """Run code context analysis on a repository.

    This function orchestrates the analysis by:
    1. Creating an agent with appropriate tools and SOP
    2. Wrapping it with ag-ui-strands for typed event streaming
    3. Streaming events to the consumer for display
    4. Returning analysis results

    Args:
        repo_path: Path to the repository to analyze.
        output_dir: Output directory for context files. Defaults to repo/.agent
        mode: Analysis mode - "fast" (default) or "deep".
        focus: Optional focus area to steer analysis (e.g., "authentication", "API layer").
        consumer: Event consumer for display. Defaults to RichEventConsumer.
        quiet: If True and no consumer, use QuietConsumer.
        use_steering: Enable progressive disclosure via steering hooks (default True).

    Returns:
        Dict with analysis status and output paths.

    Example:
        >>> result = await run_analysis("/path/to/repo", mode="fast")
        >>> print(result["output_path"])
    """
    # Setup phase
    context = _setup_analysis_context(
        repo_path,
        output_dir,
        mode,
        focus,
        consumer,
        quiet,
        use_steering,
    )

    # Build prompt
    prompt = _build_analysis_prompt(context.repo, context.output, mode, focus)

    # Execution phase
    try:
        stream_result = await _execute_analysis_stream(context, prompt)
    finally:
        await _cleanup_context(context)

    # Build final result
    context_path = context.output / "CONTEXT.md"

    return {
        "status": stream_result.status,
        "error": stream_result.error_message,
        "exceeded_limit": stream_result.exceeded_limit,
        "turn_count": stream_result.turn_count,
        "duration_seconds": stream_result.duration_seconds,
        "repo_path": str(context.repo),
        "output_dir": str(context.output),
        "context_path": str(context_path) if context_path.exists() else None,
        "mode": mode,
    }


# Event handler registry for dispatch pattern
_EVENT_HANDLERS: dict[EventType, Callable] = {}


def _register_handler(event_type: EventType):
    """Decorator to register event handlers."""

    def decorator(func: Callable):
        _EVENT_HANDLERS[event_type] = func
        return func

    return decorator


@_register_handler(EventType.RUN_STARTED)
async def _handle_run_started(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_run_started(
        getattr(event, "thread_id", ""),
        getattr(event, "run_id", ""),
    )


@_register_handler(EventType.TEXT_MESSAGE_START)
async def _handle_text_start(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_text_start(
        getattr(event, "message_id", ""),
        getattr(event, "role", "assistant"),
    )


@_register_handler(EventType.TEXT_MESSAGE_CONTENT)
async def _handle_text_content(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_text_content(
        getattr(event, "message_id", ""),
        getattr(event, "delta", ""),
    )


@_register_handler(EventType.TEXT_MESSAGE_END)
async def _handle_text_end(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_text_end(getattr(event, "message_id", ""))


@_register_handler(EventType.TOOL_CALL_START)
async def _handle_tool_start(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_tool_start(
        getattr(event, "tool_call_id", ""),
        getattr(event, "tool_call_name", ""),
    )


@_register_handler(EventType.TOOL_CALL_ARGS)
async def _handle_tool_args(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_tool_args(
        getattr(event, "tool_call_id", ""),
        getattr(event, "delta", ""),
    )


@_register_handler(EventType.TOOL_CALL_RESULT)
async def _handle_tool_result(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_tool_result(
        getattr(event, "tool_call_id", ""),
        getattr(event, "content", None),
    )


@_register_handler(EventType.TOOL_CALL_END)
async def _handle_tool_end(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_tool_end(getattr(event, "tool_call_id", ""))


@_register_handler(EventType.STATE_SNAPSHOT)
async def _handle_state_snapshot(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_state_snapshot(getattr(event, "snapshot", {}))


@_register_handler(EventType.RUN_FINISHED)
async def _handle_run_finished(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_run_finished(
        getattr(event, "thread_id", ""),
        getattr(event, "run_id", ""),
    )


@_register_handler(EventType.RUN_ERROR)
async def _handle_run_error(event: Any, consumer: EventConsumer) -> None:
    await consumer.on_error(
        getattr(event, "message", "Unknown error"),
        getattr(event, "code", None),
    )


async def _dispatch_event(event: Any, consumer: EventConsumer) -> None:
    """Dispatch an AG-UI event to the appropriate consumer method.

    Args:
        event: AG-UI event object.
        consumer: Event consumer instance.
    """
    if not hasattr(event, "type"):
        return

    handler = _EVENT_HANDLERS.get(event.type)
    if handler:
        await handler(event, consumer)


def run_analysis_sync(
    repo_path: str | Path,
    output_dir: str | Path | None = None,
    mode: str = "fast",
    quiet: bool = False,
    use_steering: bool = True,
) -> dict[str, Any]:
    """Synchronous wrapper for run_analysis.

    Args:
        repo_path: Path to the repository.
        output_dir: Output directory for context files.
        mode: Analysis mode - "fast" or "deep".
        quiet: Suppress live display.
        use_steering: Enable progressive disclosure via steering hooks (default True).

    Returns:
        Dict with analysis status and output paths.

    Example:
        >>> result = run_analysis_sync("/path/to/repo")
    """
    return asyncio.run(
        run_analysis(
            repo_path=repo_path,
            output_dir=output_dir,
            mode=mode,
            quiet=quiet,
            use_steering=use_steering,
        ),
    )
