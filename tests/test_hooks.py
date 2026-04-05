"""Tests for hook providers."""

import json
import tempfile

import pytest

from code_context_agent.agent.hooks import (
    FailFastHook,
    FullModeToolError,
    JsonLogHook,
    NarrativeQualityHook,
    OutputQualityHook,
    ReasoningCheckpointHook,
    ToolDisplayHook,
    ToolEfficiencyHook,
    create_all_hooks,
)


class TestOutputQualityHook:
    """Tests for OutputQualityHook."""

    def test_instantiates(self) -> None:
        """Test that OutputQualityHook can be created."""
        hook = OutputQualityHook()
        assert hook is not None

    def test_has_register_hooks(self) -> None:
        """Test that OutputQualityHook has register_hooks method."""
        hook = OutputQualityHook()
        assert hasattr(hook, "register_hooks")


class TestToolEfficiencyHook:
    """Tests for ToolEfficiencyHook."""

    def test_instantiates(self) -> None:
        """Test that ToolEfficiencyHook can be created."""
        hook = ToolEfficiencyHook()
        assert hook is not None

    def test_has_shell_alternatives(self) -> None:
        """Test that ToolEfficiencyHook has shell alternatives mapping."""
        hook = ToolEfficiencyHook()
        assert "grep" in hook._SHELL_ALTERNATIVES
        assert "cat " in hook._SHELL_ALTERNATIVES


class TestCreateAllHooks:
    """Tests for create_all_hooks factory."""

    def test_returns_list(self) -> None:
        """Test that create_all_hooks returns a list."""
        result = create_all_hooks()
        assert isinstance(result, list)

    def test_returns_five_hooks(self) -> None:
        """Test that create_all_hooks returns 5 hook providers by default."""
        hooks = create_all_hooks()
        assert len(hooks) == 5  # Compaction + OutputQuality + ToolEfficiency + ReasoningCheckpoint + NarrativeQuality

    def test_contains_expected_types(self) -> None:
        """Test that the hooks are the expected types."""
        hooks = create_all_hooks()
        types = {type(h) for h in hooks}
        assert OutputQualityHook in types
        assert ToolEfficiencyHook in types
        assert ReasoningCheckpointHook in types


def _make_after_event(tool_name: str, result: str | dict):
    """Create a minimal AfterToolCallEvent-like object for testing."""

    class FakeEvent:
        def __init__(self, tool_name, result):
            self.tool_use = {"name": tool_name}
            self.result = result

    return FakeEvent(tool_name, result)


class TestFullModeToolError:
    def test_inherits_runtime_error(self):
        err = FullModeToolError("lsp_start", "command not found")
        assert isinstance(err, RuntimeError)

    def test_preserves_tool_name(self):
        err = FullModeToolError("lsp_start", "command not found")
        assert err.tool_name == "lsp_start"

    def test_message_format(self):
        err = FullModeToolError("lsp_start", "command not found")
        assert "lsp_start" in str(err)
        assert "command not found" in str(err)


class TestFailFastHook:
    def test_instantiates(self):
        hook = FailFastHook()
        assert hook is not None

    def test_has_register_hooks(self):
        hook = FailFastHook()
        assert hasattr(hook, "register_hooks")

    def test_exempt_tools_contains_expected(self):
        hook = FailFastHook()
        assert "rg_search" in hook.EXEMPT_TOOLS
        assert "context7_resolve-library-id" in hook.EXEMPT_TOOLS
        assert "context7_query-docs" in hook.EXEMPT_TOOLS
        assert "shell" in hook.EXEMPT_TOOLS

    def test_raises_on_error_status(self):
        hook = FailFastHook()
        event = _make_after_event("lsp_start", json.dumps({"status": "error", "error": "not found"}))
        with pytest.raises(FullModeToolError) as exc_info:
            hook._check_for_error(event)
        assert exc_info.value.tool_name == "lsp_start"

    def test_does_not_raise_on_success(self):
        hook = FailFastHook()
        event = _make_after_event("lsp_start", json.dumps({"status": "success"}))
        hook._check_for_error(event)  # Should not raise

    def test_does_not_raise_for_exempt_tool(self):
        hook = FailFastHook()
        event = _make_after_event("rg_search", json.dumps({"status": "error", "error": "no matches"}))
        hook._check_for_error(event)  # Should not raise

    def test_does_not_raise_for_context7(self):
        hook = FailFastHook()
        event = _make_after_event("context7_resolve-library-id", json.dumps({"status": "error"}))
        hook._check_for_error(event)  # Should not raise


class TestReasoningCheckpointHook:
    """Tests for ReasoningCheckpointHook."""

    def test_instantiates(self):
        hook = ReasoningCheckpointHook()
        assert hook is not None

    def test_has_register_hooks(self):
        hook = ReasoningCheckpointHook()
        assert hasattr(hook, "register_hooks")

    def test_injects_prompt_for_git_hotspots(self):
        hook = ReasoningCheckpointHook()
        event = _make_after_event(
            "git_hotspots",
            {"status": "success", "content": [{"text": "some hotspot data here, enough length to pass"}]},
        )
        hook._inject_reasoning_prompt(event)
        assert len(event.result["content"]) == 2
        assert "REASONING CHECKPOINT" in event.result["content"][1]["text"]

    def test_no_prompt_for_untracked_tool(self):
        hook = ReasoningCheckpointHook()
        event = _make_after_event(
            "create_file_manifest",
            {"status": "success", "content": [{"text": "some data"}]},
        )
        hook._inject_reasoning_prompt(event)
        assert len(event.result["content"]) == 1

    def test_no_prompt_for_error_result(self):
        hook = ReasoningCheckpointHook()
        event = _make_after_event(
            "code_graph_analyze",
            {"status": "error", "content": [{"text": "failed"}]},
        )
        hook._inject_reasoning_prompt(event)
        assert len(event.result["content"]) == 1

    def test_no_prompt_for_empty_content(self):
        hook = ReasoningCheckpointHook()
        event = _make_after_event("code_graph_analyze", {"status": "success", "content": []})
        hook._inject_reasoning_prompt(event)
        assert len(event.result["content"]) == 0


class TestCreateAllHooksWithMode:
    def test_standard_mode_returns_five_hooks(self):
        hooks = create_all_hooks()
        assert len(hooks) == 5

    def test_full_mode_returns_six_hooks(self):
        hooks = create_all_hooks(full_mode=True)
        assert len(hooks) == 6
        assert any(isinstance(h, FailFastHook) for h in hooks)

    def test_standard_mode_no_failfast(self):
        hooks = create_all_hooks(full_mode=False)
        assert not any(isinstance(h, FailFastHook) for h in hooks)

    def test_always_has_reasoning_checkpoint(self):
        hooks_standard = create_all_hooks(full_mode=False)
        hooks_full = create_all_hooks(full_mode=True)
        assert any(isinstance(h, ReasoningCheckpointHook) for h in hooks_standard)
        assert any(isinstance(h, ReasoningCheckpointHook) for h in hooks_full)

    def test_quiet_mode_adds_json_log_hook(self):
        hooks = create_all_hooks(quiet=True)
        assert any(isinstance(h, JsonLogHook) for h in hooks)

    def test_state_mode_adds_display_hook(self):
        from code_context_agent.consumer.state import AgentDisplayState

        state = AgentDisplayState()
        hooks = create_all_hooks(state=state)
        assert any(isinstance(h, ToolDisplayHook) for h in hooks)

    def test_quiet_overrides_state(self):
        """Quiet mode uses JSON hooks even if state is provided."""
        from code_context_agent.consumer.state import AgentDisplayState

        state = AgentDisplayState()
        hooks = create_all_hooks(quiet=True, state=state)
        assert any(isinstance(h, JsonLogHook) for h in hooks)
        assert not any(isinstance(h, ToolDisplayHook) for h in hooks)

    def test_output_dir_passed_to_narrative_hook(self, tmp_path):
        """Output dir is forwarded to NarrativeQualityHook."""
        hooks = create_all_hooks(output_dir=tmp_path)
        narrative = [h for h in hooks if isinstance(h, NarrativeQualityHook)]
        assert len(narrative) == 1
        assert narrative[0]._output_dir == tmp_path

    def test_always_has_narrative_quality_hook(self):
        """NarrativeQualityHook is always included."""
        hooks_standard = create_all_hooks()
        hooks_full = create_all_hooks(full_mode=True)
        assert any(isinstance(h, NarrativeQualityHook) for h in hooks_standard)
        assert any(isinstance(h, NarrativeQualityHook) for h in hooks_full)


class TestNarrativeQualityHook:
    """Tests for NarrativeQualityHook."""

    def test_instantiates(self):
        hook = NarrativeQualityHook()
        assert hook is not None
        assert hook._pass_count == 0
        assert hook._output_dir is None

    def test_instantiates_with_output_dir(self, tmp_path):
        hook = NarrativeQualityHook(output_dir=tmp_path)
        assert hook._output_dir == tmp_path

    def test_has_register_hooks(self):
        hook = NarrativeQualityHook()
        assert hasattr(hook, "register_hooks")

    def test_heuristic_score_empty_content(self):
        """Empty content scores low."""
        score = NarrativeQualityHook._heuristic_score("")
        assert score < 1.0

    def test_heuristic_score_rich_content(self):
        """Content with headings, file refs, and diagrams scores high."""
        content = "\n".join(
            [
                "# Bundle Title",
                "",
                "## Architecture Overview",
                "The main module lives in main.py:10 and imports from config.py:5.",
                "See also utils.py:20, helpers.py:30, and core.py:1.",
                "",
                "### Data Flow",
                "```mermaid",
                "graph LR",
                "A --> B",
                "```",
                "",
                "### Entry Points",
                "```mermaid",
                "graph TD",
                "X --> Y",
                "```",
                "",
                "## Dependencies",
                "The system depends on api.py:100 for external calls.",
                "Also router.py:42, handler.py:88, and service.py:200.",
                "",
                "### Internal Dependencies",
                "Internal coupling between models.py:50 and schema.py:60.",
                "Cross-cutting in auth.py:15, logging.py:25, and middleware.py:35.",
                "",
                "## Error Handling",
                "### Exception Hierarchy",
                "Errors originate in errors.py:1 and propagate through handler.py:90.",
                "",
                "## Security Considerations",
                "### Auth Flow",
                "Token validation in auth.py:100, session.py:200, and crypto.py:300.",
                "",
                "### Input Validation",
                "Schema enforcement in validator.py:50 and sanitizer.py:75.",
                "",
            ]
            + [f"Detail line {i} covering implementation specifics." for i in range(200)],
        )
        score = NarrativeQualityHook._heuristic_score(content)
        assert score >= 3.5

    def test_heuristic_score_minimal_content(self):
        """Minimal content with no structure scores below threshold."""
        content = "Just a few lines.\nNothing here.\nNo refs."
        score = NarrativeQualityHook._heuristic_score(content)
        assert score < 3.5

    def test_skips_when_no_output_dir(self):
        """Hook does nothing when output_dir is None."""
        hook = NarrativeQualityHook(output_dir=None)

        class FakeEvent:
            resume = None

        event = FakeEvent()
        hook._check_narrative_quality(event)
        assert event.resume is None

    def test_skips_when_budget_exhausted(self):
        """Hook does nothing after max passes."""
        from pathlib import Path

        hook = NarrativeQualityHook(output_dir=Path(tempfile.mkdtemp()))
        hook._pass_count = NarrativeQualityHook.MAX_ENRICHMENT_PASSES

        class FakeEvent:
            resume = None

        event = FakeEvent()
        hook._check_narrative_quality(event)
        assert event.resume is None

    def test_skips_when_no_bundles_dir(self, tmp_path):
        """Hook does nothing when bundles/ directory doesn't exist."""
        hook = NarrativeQualityHook(output_dir=tmp_path)

        class FakeEvent:
            resume = None

        event = FakeEvent()
        hook._check_narrative_quality(event)
        assert event.resume is None

    def test_skips_when_no_bundle_files(self, tmp_path):
        """Hook does nothing when bundles/ has no BUNDLE.*.md files."""
        bundles_dir = tmp_path / "bundles"
        bundles_dir.mkdir()

        hook = NarrativeQualityHook(output_dir=tmp_path)

        class FakeEvent:
            resume = None

        event = FakeEvent()
        hook._check_narrative_quality(event)
        assert event.resume is None

    def test_triggers_enrichment_for_weak_bundles(self, tmp_path):
        """Hook sets event.resume when bundle quality is below threshold."""
        bundles_dir = tmp_path / "bundles"
        bundles_dir.mkdir()
        (bundles_dir / "BUNDLE.api.md").write_text("Thin content.\nNo refs.")

        hook = NarrativeQualityHook(output_dir=tmp_path)

        class FakeEvent:
            resume = None

        event = FakeEvent()
        hook._check_narrative_quality(event)
        assert event.resume is not None
        assert "ENRICHMENT PASS 1" in event.resume
        assert "api" in event.resume
        assert hook._pass_count == 1

    def test_passes_for_high_quality_bundles(self, tmp_path):
        """Hook does not trigger enrichment when quality is above threshold."""
        bundles_dir = tmp_path / "bundles"
        bundles_dir.mkdir()
        rich_content = "\n".join(
            [
                "## Architecture Overview",
                "### Core Modules",
                "### Data Flow",
                "### Entry Points",
                "### Dependencies",
                "### Error Handling",
                "### Security",
                "### Testing Strategy",
                "```mermaid",
                "graph LR",
                "A --> B --> C",
                "```",
                "```mermaid",
                "graph TD",
                "X --> Y",
                "```",
                "The module app.py:1 imports config.py:10, utils.py:20,",
                "models.py:30, schema.py:40, api.py:50.",
                "Also see router.py:60, handler.py:70, service.py:80,",
                "auth.py:90, middleware.py:100, errors.py:110,",
                "validator.py:120, serializer.py:130, cache.py:140,",
                "db.py:150, queue.py:160, worker.py:170,",
                "logger.py:180, monitor.py:190, health.py:200,",
                "session.py:210, crypto.py:220, rate_limiter.py:230,",
                "retry.py:240, circuit.py:250, fallback.py:260,",
                "transform.py:270, pipeline.py:280, scheduler.py:290.",
            ]
            + [f"Detailed analysis line {i} covering implementation specifics." for i in range(200)],
        )
        (bundles_dir / "BUNDLE.core.md").write_text(rich_content)

        hook = NarrativeQualityHook(output_dir=tmp_path)

        class FakeEvent:
            resume = None

        event = FakeEvent()
        hook._check_narrative_quality(event)
        assert event.resume is None
        assert hook._pass_count == 0

    def test_increments_pass_count(self, tmp_path):
        """Hook increments pass count on each enrichment trigger."""
        bundles_dir = tmp_path / "bundles"
        bundles_dir.mkdir()
        (bundles_dir / "BUNDLE.api.md").write_text("Thin.")

        hook = NarrativeQualityHook(output_dir=tmp_path)

        class FakeEvent:
            resume = None

        event1 = FakeEvent()
        hook._check_narrative_quality(event1)
        assert hook._pass_count == 1

        event2 = FakeEvent()
        hook._check_narrative_quality(event2)
        assert hook._pass_count == 2

        # Third call should be blocked by budget
        event3 = FakeEvent()
        hook._check_narrative_quality(event3)
        assert event3.resume is None
        assert hook._pass_count == 2
