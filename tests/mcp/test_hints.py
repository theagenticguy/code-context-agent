from __future__ import annotations

from code_context_agent.mcp.server import (
    EXPLORE_ACTION_HINTS,
    GRAPH_STATS_HINTS,
    QUERY_ALGORITHM_HINTS,
    _add_hints,
)

MAX_HINTS = 3


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

    def test_hints_list_bounded(self) -> None:
        for hints in QUERY_ALGORITHM_HINTS.values():
            assert 1 <= len(hints) <= MAX_HINTS, f"Algorithm hints out of bounds: {hints}"
        for hints in EXPLORE_ACTION_HINTS.values():
            assert 1 <= len(hints) <= MAX_HINTS, f"Explore hints out of bounds: {hints}"
        assert 1 <= len(GRAPH_STATS_HINTS) <= MAX_HINTS

    def test_start_analysis_hints_mention_poll(self) -> None:
        result = _add_hints(
            {"job_id": "abc123", "status": "starting"},
            [
                "Poll with check_analysis(job_id='abc123') every 30 seconds until completed",
                "If the repo was already analyzed, use query_code_graph or explore_code_graph for instant results",
            ],
        )
        assert any("check_analysis" in h for h in result["next_steps"])

    def test_query_hotspots_has_expand_hint(self) -> None:
        hints = QUERY_ALGORITHM_HINTS["hotspots"]
        assert any("expand_node" in h for h in hints)
