"""Hook providers for agent guidance and quality control.

This module provides HookProvider implementations that integrate with
the Strands hook system for contextual guidance during agent execution.

Uses stable strands.agent.hooks API (not experimental steering).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from pathlib import Path

    from ..consumer.state import AgentDisplayState

from loguru import logger
from strands.hooks import (
    AfterToolCallEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
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
    "gitnexus_query": (
        "[REASONING CHECKPOINT] Which search results are most relevant to the investigation? "
        "Look at confidence scores and process groupings. Symbols appearing in multiple processes "
        "are likely core business logic. Plan which symbols to expand with gitnexus_context."
    ),
    "gitnexus_context": (
        "[REASONING CHECKPOINT] What does this symbol's relationship map reveal? "
        "High incoming relationships = widely depended on (foundational). "
        "High outgoing = orchestrator/coordinator. "
        "Process participation across multiple flows = critical business logic."
    ),
    "gitnexus_impact": (
        "[REASONING CHECKPOINT] How wide is the blast radius? "
        "Depth-1 impacts are direct risks. Depth-2+ are cascading risks. "
        "Cross-reference with git_hotspots — high churn + wide blast radius = fragile bottleneck."
    ),
    "git_hotspots": (
        "[REASONING CHECKPOINT] Which high-churn files overlap with structurally important symbols from GitNexus? "
        "High churn + high relationship count = fragile bottleneck. Note any files that are hot but structurally "
        "peripheral (may indicate config thrash or generated code)."
    ),
    "git_files_changed_together": (
        "[REASONING CHECKPOINT] Do these co-change patterns match the structural dependencies from GitNexus? "
        "Files that change together WITHOUT a structural relationship indicate an implicit coupling "
        "that an AI coding assistant must know about."
    ),
    "git_blame_summary": (
        "[REASONING CHECKPOINT] What does the ownership distribution reveal? "
        "Single-author files with high centrality = bus factor risk. "
        "Many-author files with complex logic = coordination risk."
    ),
    "read_file_bounded": (
        "[REASONING CHECKPOINT] Now that you have read this code, compare what you see against "
        "what GitNexus context/impact data predicted. Does the code complexity match its structural importance? "
        "What domain invariants does this file maintain? What would break if it were changed naively?"
    ),
    "write_bundle": (
        "[ENRICHMENT CHECKPOINT] Before writing the next bundle or finishing, review what you just wrote. "
        "1) Does every claim have a file:line reference? "
        "2) Did you cross-reference this area with findings from other teams? "
        "3) What would a developer find surprising here that you haven't mentioned? "
        "4) What cross-cutting concerns (error handling, logging, auth) span this area and others? "
        "After writing each bundle, call score_narrative to evaluate quality. "
        "If the score is below 3.5, call enrich_bundle and rewrite."
    ),
}


class FullModeToolError(RuntimeError):
    """Raised by FailFastHook when a critical tool returns an error in full mode."""

    def __init__(self, tool_name: str, error_message: str) -> None:  # noqa: D107
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' failed: {error_message}")


class OutputQualityHook(HookProvider):
    """Hook for output quality enforcement.

    Logs warnings when tool outputs are unusually large.
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


class ConversationCompactionHook(HookProvider):
    """Strips large toolUse/toolResult payloads from conversation history.

    After the model has seen and reasoned about tool results, the raw
    payloads are no longer needed — only the model's reasoning matters.
    Before each model invocation, this hook walks the message history and
    replaces large tool payloads with stubs, keeping all text/reasoning
    turns intact.

    This prevents context window overflow from accumulated tool results
    without ever truncating data the model hasn't seen yet.
    """

    COMPACTION_THRESHOLD = 2000  # chars — compact payloads larger than this
    KEEP_RECENT_MESSAGES = 4  # keep last N messages uncompacted (current turn)

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register conversation compaction callback."""
        from strands.hooks.events import BeforeInvocationEvent

        registry.add_callback(BeforeInvocationEvent, self._compact_history)

    def _compact_history(self, event: Any, **kwargs: Any) -> None:
        """Strip large tool payloads from older messages before model invocation."""
        messages = getattr(event, "messages", None)
        if not messages:
            return

        # Only compact older messages — keep recent ones intact for current reasoning
        boundary = max(0, len(messages) - self.KEEP_RECENT_MESSAGES)
        compacted = 0

        for i in range(boundary):
            content = messages[i].get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                compacted += self._compact_tool_result(block)
                compacted += self._compact_tool_use(block)

        if compacted:
            logger.info(f"Compacted {compacted} large tool payloads from conversation history")

    def _compact_tool_result(self, block: dict[str, Any]) -> int:
        """Replace large toolResult content with a stub. Returns 1 if compacted."""
        if "toolResult" not in block:
            return 0
        tool_result = block["toolResult"]
        result_content = tool_result.get("content", [])
        total = sum(len(rc.get("text", "")) for rc in result_content if isinstance(rc, dict))
        if total <= self.COMPACTION_THRESHOLD:
            return 0
        stub = f"[Tool output consumed ({total} chars) — see reasoning above]"
        tool_result["content"] = [{"text": stub}]
        logger.debug(f"Compacted toolResult {tool_result.get('toolUseId', '?')}: {total} chars")
        return 1

    def _compact_tool_use(self, block: dict[str, Any]) -> int:
        """Replace large toolUse input with a stub. Returns 1 if compacted."""
        if "toolUse" not in block:
            return 0
        tool_use = block["toolUse"]
        input_str = str(tool_use.get("input", ""))
        if len(input_str) <= self.COMPACTION_THRESHOLD:
            return 0
        tool_use["input"] = {"_compacted": True, "tool": tool_use.get("name", "?")}
        logger.debug(f"Compacted toolUse input for {tool_use.get('name', '?')}: {len(input_str)} chars")
        return 1


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

        if tool_name in self.EXEMPT_TOOLS or tool_name.startswith(("context7_", "gitnexus_")):
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


class TeamDispatchHook(HookProvider):
    """Hook that tracks dispatch_team tool calls for TUI display.

    Updates AgentDisplayState with team dispatch/completion information
    so the coordinator display can show team progress.
    """

    def __init__(self, state: AgentDisplayState) -> None:  # noqa: D107
        self._state = state

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register team dispatch callbacks."""
        registry.add_callback(BeforeToolCallEvent, self._on_dispatch_start)
        registry.add_callback(AfterToolCallEvent, self._on_dispatch_end)

    def _on_dispatch_start(self, event: BeforeToolCallEvent, **kwargs: Any) -> None:
        """Track when a team is dispatched."""
        tool_name = event.tool_use.get("name", "")
        if tool_name != "dispatch_team":
            return

        args = event.tool_use.get("input", {})
        if not isinstance(args, dict):
            return

        team_id = args.get("team_id", "unknown")
        mandate = args.get("mandate", "")
        agents = args.get("agents", [])
        agent_count = len(agents) if isinstance(agents, list) else 0

        self._state.start_team(team_id, mandate, agent_count)
        logger.debug(f"Team dispatched: {team_id} ({agent_count} agents)")

    def _on_dispatch_end(self, event: AfterToolCallEvent, **kwargs: Any) -> None:
        """Track when a team dispatch completes."""
        tool_name = event.tool_use.get("name", "")
        if tool_name != "dispatch_team":
            return

        args = event.tool_use.get("input", {})
        if not isinstance(args, dict):
            return

        team_id = args.get("team_id", "unknown")
        is_error = _is_error_result(event.result)
        status = "error" if is_error else "done"

        self._state.complete_team(team_id, status=status)
        logger.debug(f"Team completed: {team_id} (status={status})")


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


class NarrativeQualityHook(HookProvider):
    """Hook that triggers enrichment passes when narrative quality is below threshold.

    After the coordinator finishes an invocation, checks if bundles exist and scores
    them. If average quality is below threshold, triggers a re-invocation via
    event.resume with enrichment instructions.

    Max 2 enrichment passes to avoid infinite loops.
    """

    MAX_ENRICHMENT_PASSES = 2
    QUALITY_THRESHOLD = 3.5  # Out of 5.0

    def __init__(self, output_dir: Path | None = None) -> None:  # noqa: D107
        self._pass_count = 0
        self._output_dir = output_dir

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register narrative quality check callback."""
        from strands.hooks.events import AfterInvocationEvent

        registry.add_callback(AfterInvocationEvent, self._check_narrative_quality)

    def _check_narrative_quality(self, event: Any, **kwargs: Any) -> None:
        """Check bundle quality after coordinator invocation and trigger enrichment if needed."""
        if self._pass_count >= self.MAX_ENRICHMENT_PASSES:
            return  # Budget exhausted

        if not self._output_dir:
            return

        bundles_dir = self._output_dir / "bundles"
        if not bundles_dir.exists():
            return

        # Score all bundles
        bundle_files = list(bundles_dir.glob("BUNDLE.*.md"))
        if not bundle_files:
            return

        scores: list[float] = []
        weak_bundles: list[tuple[str, float]] = []
        for bf in bundle_files:
            content = bf.read_text()
            score = self._heuristic_score(content)
            scores.append(score)
            area = bf.stem.replace("BUNDLE.", "")
            if score < self.QUALITY_THRESHOLD:
                weak_bundles.append((area, score))

        avg_score = sum(scores) / len(scores) if scores else 0.0

        if avg_score >= self.QUALITY_THRESHOLD and not weak_bundles:
            logger.info(f"Narrative quality check passed: avg={avg_score:.1f}/5.0")
            return

        # Trigger enrichment pass
        self._pass_count += 1
        weak_list = ", ".join(f"{a} ({s:.1f})" for a, s in weak_bundles)

        event.resume = (
            f"[ENRICHMENT PASS {self._pass_count}/{self.MAX_ENRICHMENT_PASSES}] "
            f"Quality check: avg score {avg_score:.1f}/5.0. "
            f"Weak bundles: {weak_list}. "
            "For each weak bundle: "
            "1) Call score_narrative(area) to get detailed dimension scores. "
            "2) Call enrich_bundle(area, feedback) with the suggestions. "
            "3) Rewrite the bundle via write_bundle with richer content. "
            "4) Call score_narrative again to verify improvement. "
            "Focus on adding file:line references, cross-cutting insights, and surprising findings."
        )
        logger.info(
            f"Narrative enrichment pass {self._pass_count} triggered: "
            f"avg={avg_score:.1f}, weak={len(weak_bundles)} bundles",
        )

    @staticmethod
    def _heuristic_score(content: str) -> float:
        """Quick heuristic score for a bundle (0.0-5.0).

        Scores based on four dimensions:
        - depth_score: Line count (longer = more detailed)
        - spec_score: File:line references (specificity)
        - struct_score: Heading count (structure)
        - diag_score: Mermaid diagram count (visual aids)

        Args:
            content: Bundle markdown content.

        Returns:
            Score from 0.0 to 5.0.
        """
        import re

        lines = content.split("\n")
        line_count = len(lines)
        file_refs = len(re.findall(r"\w+\.\w+:\d+", content))
        headings = sum(1 for line in lines if line.startswith("## ") or line.startswith("### "))
        mermaid = content.count("```mermaid")

        # Simple scoring
        depth_score = min(5.0, line_count / 40)
        spec_score = min(5.0, file_refs / 5)
        struct_score = min(5.0, headings / 2)
        diag_score = min(5.0, mermaid * 2.5) if mermaid else 1.0

        return (depth_score + spec_score + struct_score + diag_score) / 4


def create_all_hooks(
    *,
    full_mode: bool = False,
    state: Any | None = None,
    quiet: bool = False,
    output_dir: Path | None = None,
) -> list[HookProvider]:
    """Create all hook providers for agent guidance and display.

    Returns a flat list of hook providers to register on the agent.

    Args:
        full_mode: If True, include FailFastHook.
        state: AgentDisplayState for TUI display. None if quiet mode.
        quiet: If True, use JsonLogHook instead of display hooks.
        output_dir: Output directory for narrative quality checks. None disables
            NarrativeQualityHook scoring.

    Returns:
        List of HookProvider instances.
    """
    hooks: list[HookProvider] = [
        ConversationCompactionHook(),
        OutputQualityHook(),
        ToolEfficiencyHook(),
        ReasoningCheckpointHook(),
        NarrativeQualityHook(output_dir=output_dir),
    ]
    if full_mode:
        hooks.append(FailFastHook())

    # Display hooks
    if quiet:
        hooks.append(JsonLogHook())
    elif state is not None:
        hooks.append(ToolDisplayHook(state))
        hooks.append(TeamDispatchHook(state))

    return hooks
