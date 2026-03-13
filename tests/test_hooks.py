"""Tests for hook providers."""

import json

import pytest

from code_context_agent.agent.hooks import (
    FailFastHook,
    FullModeToolError,
    OutputQualityHook,
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
        hooks = create_all_hooks()
        assert isinstance(hooks, list)

    def test_returns_two_hooks(self) -> None:
        """Test that create_all_hooks returns 2 hook providers."""
        hooks = create_all_hooks()
        assert len(hooks) == 2  # noqa: PLR2004

    def test_contains_expected_types(self) -> None:
        """Test that the hooks are the expected types."""
        hooks = create_all_hooks()
        types = {type(h) for h in hooks}
        assert OutputQualityHook in types
        assert ToolEfficiencyHook in types


def _make_after_event(tool_name: str, result_str: str):
    """Create a minimal AfterToolCallEvent-like object for testing."""

    class FakeEvent:
        def __init__(self, tool_name, result_str):
            self.tool_use = {"name": tool_name}
            self.result = result_str

    return FakeEvent(tool_name, result_str)


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


class TestCreateAllHooksWithMode:
    def test_standard_mode_returns_two_hooks(self):
        hooks = create_all_hooks()
        assert len(hooks) == 2  # noqa: PLR2004

    def test_full_mode_returns_three_hooks(self):
        hooks = create_all_hooks(full_mode=True)
        assert len(hooks) == 3  # noqa: PLR2004
        assert any(isinstance(h, FailFastHook) for h in hooks)

    def test_standard_mode_no_failfast(self):
        hooks = create_all_hooks(full_mode=False)
        assert not any(isinstance(h, FailFastHook) for h in hooks)
