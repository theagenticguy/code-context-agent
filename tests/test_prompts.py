"""Tests for prompt rendering from Jinja2 templates."""

import pytest

from code_context_agent.agent.prompts import get_prompt, get_steering_content


class TestGetPrompt:
    """Tests for the unified system prompt."""

    def test_renders_nonempty(self) -> None:
        """Test that get_prompt returns non-empty content."""
        prompt = get_prompt()
        assert len(prompt) > 100

    def test_contains_rules(self) -> None:
        """Test that prompt includes the rules section."""
        prompt = get_prompt()
        assert "## Rules" in prompt

    def test_contains_phases(self) -> None:
        """Test that prompt includes analysis phases."""
        prompt = get_prompt()
        assert "## Analysis Phases" in prompt

    def test_contains_exit_gate(self) -> None:
        """Test that prompt includes exit gate."""
        prompt = get_prompt()
        assert "## Exit Gate" in prompt

    def test_contains_tool_docs(self) -> None:
        """Test that prompt includes tool documentation."""
        prompt = get_prompt()
        assert "ast-grep" in prompt
        assert "Code Graph" in prompt
        assert "Git History" in prompt

    def test_contains_output_format(self) -> None:
        """Test that prompt includes output format rules."""
        prompt = get_prompt()
        assert "Mermaid limits" in prompt


class TestGetSteeringContent:
    """Tests for steering fragment rendering."""

    def test_size_limits(self) -> None:
        """Test that size_limits fragment renders."""
        content = get_steering_content("size_limits")
        assert "SIZE LIMITS" in content
        assert "CONTEXT.md" in content

    def test_conciseness(self) -> None:
        """Test that conciseness fragment renders."""
        content = get_steering_content("conciseness")
        assert "CONCISENESS" in content

    def test_anti_patterns(self) -> None:
        """Test that anti_patterns fragment renders."""
        content = get_steering_content("anti_patterns")
        assert "ANTI-PATTERNS" in content

    def test_tool_efficiency(self) -> None:
        """Test that tool_efficiency fragment renders."""
        content = get_steering_content("tool_efficiency")
        assert "TOOL EFFICIENCY" in content

    def test_graph_exploration(self) -> None:
        """Test that graph_exploration fragment renders."""
        content = get_steering_content("graph_exploration")
        assert "GRAPH EXPLORATION" in content

    def test_invalid_name_raises(self) -> None:
        """Test that invalid fragment name raises error."""
        from jinja2 import TemplateNotFound

        with pytest.raises(TemplateNotFound):
            get_steering_content("nonexistent_fragment")
