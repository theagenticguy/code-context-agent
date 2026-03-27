"""Tests for mode-aware prompt rendering."""

from code_context_agent.agent.prompts import get_prompt, get_steering_content


class TestGetPromptFullMode:
    def test_standard_mode_has_size_limits(self):
        prompt = get_prompt(mode="standard")
        assert "SIZE LIMITS" in prompt

    def test_full_mode_omits_size_limits(self):
        prompt = get_prompt(mode="full")
        assert "SIZE LIMITS" not in prompt

    def test_full_mode_has_exhaustive_directives(self):
        prompt = get_prompt(mode="full")
        assert "EXHAUSTIVE" in prompt or "exhaustive" in prompt

    def test_full_mode_has_context7_directive(self):
        prompt = get_prompt(mode="full")
        assert "context7" in prompt.lower()

    def test_full_mode_has_no_skip_conditions(self):
        prompt = get_prompt(mode="full")
        # Full mode should not tell the agent to skip things
        lower = prompt.lower()
        assert "do not skip" in lower or "skip if" not in lower

    def test_default_mode_unchanged(self):
        """get_prompt() with no args still works as before."""
        prompt = get_prompt()
        assert "## Analysis Phases" in prompt
        assert "## Exit Gate" in prompt

    def test_full_mode_still_has_phases(self):
        prompt = get_prompt(mode="full")
        assert "## Analysis Phases" in prompt

    def test_full_plus_focus_gets_full_steering(self):
        """full+focus mode must include exhaustive directives, not size limits."""
        prompt = get_prompt(mode="full+focus")
        assert "EXHAUSTIVE" in prompt or "exhaustive" in prompt
        assert "SIZE LIMITS" not in prompt


class TestGetSteeringContentFullMode:
    def test_full_mode_fragment_exists(self):
        content = get_steering_content("full_mode")
        assert len(content) > 50
