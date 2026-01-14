"""Agent runner with event streaming and display.

This module provides functions to run the analysis agent and stream
events to consumers for display or further processing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from ag_ui.core import EventType
from ag_ui_strands import StrandsAgent

from ..config import get_settings
from ..consumer import EventConsumer, QuietConsumer, RichEventConsumer
from .factory import create_agent

logger = logging.getLogger(__name__)

# Default execution bounds (can be overridden by config)
DEFAULT_MAX_TURNS = 100
DEFAULT_MAX_DURATION = 600  # 10 minutes


async def run_analysis(  # noqa: PLR0915 - cohesive analysis workflow
    repo_path: str | Path,
    output_dir: str | Path | None = None,
    mode: str = "fast",
    consumer: EventConsumer | None = None,
    quiet: bool = False,
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
        consumer: Event consumer for display. Defaults to RichEventConsumer.
        quiet: If True and no consumer, use QuietConsumer.

    Returns:
        Dict with analysis status and output paths.

    Example:
        >>> result = await run_analysis("/path/to/repo", mode="fast")
        >>> print(result["output_path"])
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
    strands_agent = create_agent(mode=mode)

    # Wrap with ag-ui-strands for typed event streaming
    agui_agent = StrandsAgent(
        agent=strands_agent,
        name="code_context_agent",
        description=f"Code context analysis agent ({mode} mode)",
    )

    # Build the analysis prompt
    prompt = f"""
Analyze the repository at: {repo}

Output all files to: {output}

Mode: {mode.upper()}

Follow your SOP to produce the narrated context bundle.
Start with Phase 0 (create_file_manifest) and proceed through all phases.
"""

    # Build input for ag-ui
    from ag_ui.core import RunAgentInput, UserMessage

    input_data = RunAgentInput(
        thread_id="analysis-thread",
        run_id=f"run-{mode}",
        messages=[UserMessage(id="msg-1", role="user", content=prompt)],
        state={},  # Initial empty state
        tools=[],  # Tools are provided by the agent, not the input
        context=[],  # No additional context
        forwarded_props={},  # No forwarded props
    )

    # Start consumer display
    await consumer.start()

    # Get execution bounds from settings
    settings = get_settings()
    max_turns = getattr(settings, "agent_max_turns", DEFAULT_MAX_TURNS)
    max_duration = getattr(settings, "agent_max_duration", DEFAULT_MAX_DURATION)

    start_time = time.monotonic()
    turn_count = 0
    exceeded_limit: str | None = None
    error_message: str | None = None

    try:
        # Stream events from ag-ui-strands
        async for event in agui_agent.run(input_data):
            turn_count += 1
            elapsed = time.monotonic() - start_time

            # Check turn limit
            if turn_count > max_turns:
                logger.warning(f"Agent exceeded {max_turns} turns, stopping")
                exceeded_limit = f"max_turns ({max_turns})"
                break

            # Check time limit
            if elapsed > max_duration:
                logger.warning(f"Agent exceeded {max_duration}s duration, stopping")
                exceeded_limit = f"max_duration ({max_duration}s)"
                break

            await _dispatch_event(event, consumer)

            # Check for error
            if hasattr(event, "type") and event.type == EventType.RUN_ERROR:
                error_message = getattr(event, "message", "Unknown error")
                break

    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        logger.error(f"Analysis error: {e}\n{tb}")
        error_message = str(e) if str(e) else f"{type(e).__name__}: {tb}"
        await consumer.on_error(error_message)

    finally:
        await consumer.stop()

        # Cleanup LSP sessions
        from ..tools.lsp.session import get_session_manager

        await get_session_manager().shutdown_all()

    # Calculate final duration
    final_duration = time.monotonic() - start_time

    # Return results
    context_path = output / "CONTEXT.md"

    # Determine status
    if error_message:
        status = "error"
    elif exceeded_limit:
        status = "stopped"
    else:
        status = "completed"

    return {
        "status": status,
        "error": error_message,
        "exceeded_limit": exceeded_limit,
        "turn_count": turn_count,
        "duration_seconds": final_duration,
        "repo_path": str(repo),
        "output_dir": str(output),
        "context_path": str(context_path) if context_path.exists() else None,
        "mode": mode,
    }


async def _dispatch_event(event: Any, consumer: EventConsumer) -> None:
    """Dispatch an AG-UI event to the appropriate consumer method.

    Args:
        event: AG-UI event object.
        consumer: Event consumer instance.
    """
    if not hasattr(event, "type"):
        return

    event_type = event.type

    match event_type:
        case EventType.RUN_STARTED:
            await consumer.on_run_started(
                getattr(event, "thread_id", ""),
                getattr(event, "run_id", ""),
            )

        case EventType.TEXT_MESSAGE_START:
            await consumer.on_text_start(
                getattr(event, "message_id", ""),
                getattr(event, "role", "assistant"),
            )

        case EventType.TEXT_MESSAGE_CONTENT:
            await consumer.on_text_content(
                getattr(event, "message_id", ""),
                getattr(event, "delta", ""),
            )

        case EventType.TEXT_MESSAGE_END:
            await consumer.on_text_end(getattr(event, "message_id", ""))

        case EventType.TOOL_CALL_START:
            await consumer.on_tool_start(
                getattr(event, "tool_call_id", ""),
                getattr(event, "tool_call_name", ""),
            )

        case EventType.TOOL_CALL_ARGS:
            await consumer.on_tool_args(
                getattr(event, "tool_call_id", ""),
                getattr(event, "delta", ""),
            )

        case EventType.TOOL_CALL_RESULT:
            await consumer.on_tool_result(
                getattr(event, "tool_call_id", ""),
                getattr(event, "content", None),
            )

        case EventType.TOOL_CALL_END:
            await consumer.on_tool_end(getattr(event, "tool_call_id", ""))

        case EventType.STATE_SNAPSHOT:
            await consumer.on_state_snapshot(getattr(event, "snapshot", {}))

        case EventType.RUN_FINISHED:
            await consumer.on_run_finished(
                getattr(event, "thread_id", ""),
                getattr(event, "run_id", ""),
            )

        case EventType.RUN_ERROR:
            await consumer.on_error(
                getattr(event, "message", "Unknown error"),
                getattr(event, "code", None),
            )


def run_analysis_sync(
    repo_path: str | Path,
    output_dir: str | Path | None = None,
    mode: str = "fast",
    quiet: bool = False,
) -> dict[str, Any]:
    """Synchronous wrapper for run_analysis.

    Args:
        repo_path: Path to the repository.
        output_dir: Output directory for context files.
        mode: Analysis mode - "fast" or "deep".
        quiet: Suppress live display.

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
        )
    )
