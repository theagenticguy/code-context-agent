"""Tests for hook providers."""

from code_context_agent.agent.hooks import (
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
