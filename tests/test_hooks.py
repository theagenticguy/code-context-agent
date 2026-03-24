"""Tests for hook providers."""

import json

import pytest

from code_context_agent.agent.hooks import (
    FailFastHook,
    FullModeToolError,
    JsonLogHook,
    JsonLogSwarmHook,
    OutputQualityHook,
    ReasoningCheckpointHook,
    SwarmDisplayHook,
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

    def test_returns_tuple(self) -> None:
        """Test that create_all_hooks returns a tuple of two lists."""
        result = create_all_hooks()
        assert isinstance(result, tuple)
        assert len(result) == 2
        agent_hooks, swarm_hooks = result
        assert isinstance(agent_hooks, list)
        assert isinstance(swarm_hooks, list)

    def test_returns_four_agent_hooks(self) -> None:
        """Test that create_all_hooks returns 4 agent hook providers by default."""
        agent_hooks, swarm_hooks = create_all_hooks()
        assert len(agent_hooks) == 4  # Compaction + OutputQuality + ToolEfficiency + ReasoningCheckpoint
        assert len(swarm_hooks) == 0

    def test_contains_expected_types(self) -> None:
        """Test that the agent hooks are the expected types."""
        agent_hooks, _ = create_all_hooks()
        types = {type(h) for h in agent_hooks}
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
        assert "lsp_shutdown" in hook.EXEMPT_TOOLS
        assert "rg_search" in hook.EXEMPT_TOOLS
        assert "code_graph_load" in hook.EXEMPT_TOOLS
        assert "context7_resolve-library-id" in hook.EXEMPT_TOOLS
        assert "context7_query-docs" in hook.EXEMPT_TOOLS

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

    def test_injects_prompt_for_graph_analyze(self):
        hook = ReasoningCheckpointHook()
        event = _make_after_event(
            "code_graph_analyze",
            {"status": "success", "content": [{"text": json.dumps({"hotspots": [{"name": "foo"}]})}]},
        )
        hook._inject_reasoning_prompt(event)
        # Should have appended a reasoning checkpoint text block
        assert len(event.result["content"]) == 2
        assert "REASONING CHECKPOINT" in event.result["content"][1]["text"]

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
    def test_standard_mode_returns_four_agent_hooks(self):
        agent_hooks, swarm_hooks = create_all_hooks()
        assert len(agent_hooks) == 4
        assert len(swarm_hooks) == 0

    def test_full_mode_returns_five_agent_hooks(self):
        agent_hooks, _ = create_all_hooks(full_mode=True)
        assert len(agent_hooks) == 5
        assert any(isinstance(h, FailFastHook) for h in agent_hooks)

    def test_standard_mode_no_failfast(self):
        agent_hooks, _ = create_all_hooks(full_mode=False)
        assert not any(isinstance(h, FailFastHook) for h in agent_hooks)

    def test_always_has_reasoning_checkpoint(self):
        agent_hooks_standard, _ = create_all_hooks(full_mode=False)
        agent_hooks_full, _ = create_all_hooks(full_mode=True)
        assert any(isinstance(h, ReasoningCheckpointHook) for h in agent_hooks_standard)
        assert any(isinstance(h, ReasoningCheckpointHook) for h in agent_hooks_full)

    def test_quiet_mode_adds_json_log_hooks(self):
        agent_hooks, swarm_hooks = create_all_hooks(quiet=True)
        assert any(isinstance(h, JsonLogHook) for h in agent_hooks)
        assert any(isinstance(h, JsonLogSwarmHook) for h in swarm_hooks)

    def test_state_mode_adds_display_hooks(self):
        from code_context_agent.consumer.state import AgentDisplayState

        state = AgentDisplayState()
        agent_hooks, swarm_hooks = create_all_hooks(state=state)
        assert any(isinstance(h, ToolDisplayHook) for h in agent_hooks)
        assert any(isinstance(h, SwarmDisplayHook) for h in swarm_hooks)

    def test_quiet_overrides_state(self):
        """Quiet mode uses JSON hooks even if state is provided."""
        from code_context_agent.consumer.state import AgentDisplayState

        state = AgentDisplayState()
        agent_hooks, _swarm_hooks = create_all_hooks(quiet=True, state=state)
        assert any(isinstance(h, JsonLogHook) for h in agent_hooks)
        assert not any(isinstance(h, ToolDisplayHook) for h in agent_hooks)
