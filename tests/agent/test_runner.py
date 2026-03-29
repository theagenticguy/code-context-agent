"""Tests for analysis prompt builder."""

from code_context_agent.agent.runner import _build_analysis_prompt


class TestBuildAnalysisPrompt:
    def test_no_focus_produces_standard_prompt(self):
        """Without focus, prompt mentions standard workflow."""
        prompt = _build_analysis_prompt(focus=None)
        assert "Begin analysis" in prompt
        assert "heuristic summary" in prompt

    def test_focus_appears_in_prompt(self):
        """Focus area is included in the prompt."""
        prompt = _build_analysis_prompt(focus="authentication")
        assert "FOCUS AREA: authentication" in prompt

    def test_issue_context_appears_in_prompt(self):
        """Issue context is appended to prompt."""
        prompt = _build_analysis_prompt(
            focus=None,
            issue_context="<issue>Bug in auth</issue>",
        )
        assert "Issue Context" in prompt
        assert "Bug in auth" in prompt

    def test_focus_combined_with_issue(self):
        """Both focus and issue_context appear in prompt."""
        prompt = _build_analysis_prompt(
            focus="authentication",
            issue_context="<issue>Login fails</issue>",
        )
        assert "FOCUS AREA: authentication" in prompt
        assert "Issue Context" in prompt

    def test_bundles_only_mode(self):
        """Bundles-only mode skips team dispatch."""
        prompt = _build_analysis_prompt(focus=None, bundles_only=True)
        assert "Bundles-only mode" in prompt
        assert "read_team_findings" in prompt
        assert "Begin analysis" not in prompt

    def test_bundles_only_with_focus(self):
        """Bundles-only mode still includes focus."""
        prompt = _build_analysis_prompt(focus="security", bundles_only=True)
        assert "Bundles-only mode" in prompt
        assert "FOCUS AREA: security" in prompt
