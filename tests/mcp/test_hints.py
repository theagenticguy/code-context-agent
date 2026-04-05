from __future__ import annotations

from code_context_agent.mcp.server import _add_hints


class TestAddHints:
    def test_add_hints_appends_next_steps(self) -> None:
        result = _add_hints({}, ["hint1", "hint2"])
        assert "next_steps" in result
        assert result["next_steps"] == ["hint1", "hint2"]

    def test_add_hints_preserves_existing_data(self) -> None:
        original = {"algorithm": "hotspots", "results": [1, 2, 3]}
        result = _add_hints(original, ["hint"])
        assert result["algorithm"] == "hotspots"
        assert result["results"] == [1, 2, 3]
        assert result["next_steps"] == ["hint"]

    def test_start_analysis_hints_mention_poll(self) -> None:
        result = _add_hints(
            {"job_id": "abc123", "status": "starting"},
            [
                "Poll with check_analysis(job_id='abc123') every 30 seconds until completed",
                "While waiting, use GitNexus tools for immediate structural queries",
            ],
        )
        assert any("check_analysis" in h for h in result["next_steps"])
