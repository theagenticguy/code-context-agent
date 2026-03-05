"""Tests for analysis prompt builder with incremental context."""

from pathlib import Path

from code_context_agent.agent.runner import _build_analysis_prompt


class TestBuildAnalysisPromptIncremental:
    def test_includes_since_context(self):
        """since_context is appended to prompt."""
        prompt = _build_analysis_prompt(
            repo=Path("/repo"),
            output=Path("/repo/.code-context"),
            focus=None,
            since_context="<since_context><ref>HEAD~5</ref></since_context>",
        )
        assert "Incremental Analysis Mode" in prompt
        assert "<since_context>" in prompt
        assert "HEAD~5" in prompt

    def test_no_since_context_produces_normal_prompt(self):
        """Without since_context, prompt has no incremental section."""
        prompt = _build_analysis_prompt(
            repo=Path("/repo"),
            output=Path("/repo/.code-context"),
            focus=None,
        )
        assert "Incremental Analysis Mode" not in prompt

    def test_since_combined_with_focus(self):
        """Both focus and since_context appear in prompt."""
        prompt = _build_analysis_prompt(
            repo=Path("/repo"),
            output=Path("/repo/.code-context"),
            focus="authentication",
            since_context="<since_context><ref>main</ref></since_context>",
        )
        assert "FOCUS AREA: authentication" in prompt
        assert "Incremental Analysis Mode" in prompt

    def test_since_combined_with_issue(self):
        """Both issue and since_context appear in prompt."""
        prompt = _build_analysis_prompt(
            repo=Path("/repo"),
            output=Path("/repo/.code-context"),
            focus=None,
            issue_context="<issue>Bug in auth</issue>",
            since_context="<since_context><ref>HEAD~3</ref></since_context>",
        )
        assert "Issue Context" in prompt
        assert "Incremental Analysis Mode" in prompt

    def test_incremental_prompt_mentions_code_graph_load(self):
        """Incremental prompt instructs agent to load existing graph."""
        prompt = _build_analysis_prompt(
            repo=Path("/repo"),
            output=Path("/repo/.code-context"),
            focus=None,
            since_context="<since_context><ref>HEAD~1</ref></since_context>",
        )
        assert "code_graph_load" in prompt
        assert "code_graph_ingest_git" in prompt
