"""Tests for analysis phase detection."""

from __future__ import annotations

from code_context_agent.consumer.phases import (
    PHASE_DESCRIPTIONS,
    PHASE_NAMES,
    TOOL_PHASE_MAP,
    AnalysisPhase,
    PhaseState,
    resolve_phase,
)


class TestAnalysisPhase:
    def test_enum_ordering(self):
        assert AnalysisPhase.FOUNDATION < AnalysisPhase.SEMANTIC_DISCOVERY
        assert AnalysisPhase.WRITE_CONTEXT == 10  # noqa: PLR2004

    def test_all_ten_phases(self):
        assert len(AnalysisPhase) == 10  # noqa: PLR2004


class TestToolPhaseMap:
    def test_file_manifest_maps_to_foundation(self):
        assert TOOL_PHASE_MAP["create_file_manifest"] == AnalysisPhase.FOUNDATION

    def test_lsp_start_maps_to_semantic(self):
        assert TOOL_PHASE_MAP["lsp_start"] == AnalysisPhase.SEMANTIC_DISCOVERY

    def test_astgrep_maps_to_pattern(self):
        assert TOOL_PHASE_MAP["astgrep_scan"] == AnalysisPhase.PATTERN_DISCOVERY

    def test_git_maps_to_history(self):
        assert TOOL_PHASE_MAP["git_hotspots"] == AnalysisPhase.GIT_HISTORY

    def test_graph_create_maps_to_graph(self):
        assert TOOL_PHASE_MAP["code_graph_create"] == AnalysisPhase.GRAPH_ANALYSIS

    def test_write_file_maps_to_context(self):
        assert TOOL_PHASE_MAP["write_file"] == AnalysisPhase.WRITE_CONTEXT


class TestPhaseNames:
    def test_all_phases_have_names(self):
        for phase in AnalysisPhase:
            assert phase in PHASE_NAMES

    def test_all_phases_have_descriptions(self):
        for phase in AnalysisPhase:
            assert phase in PHASE_DESCRIPTIONS


class TestPhaseState:
    def test_creation(self):
        ps = PhaseState(phase=AnalysisPhase.FOUNDATION, name="Foundation", description="desc", started_at=100.0)
        assert ps.phase == AnalysisPhase.FOUNDATION
        assert ps.completed_at is None

    def test_is_complete(self):
        ps = PhaseState(phase=AnalysisPhase.FOUNDATION, name="Foundation", description="desc", started_at=100.0)
        assert not ps.is_complete
        ps.completed_at = 110.0
        assert ps.is_complete

    def test_elapsed_seconds(self):
        ps = PhaseState(
            phase=AnalysisPhase.FOUNDATION,
            name="Foundation",
            description="desc",
            started_at=100.0,
            completed_at=115.5,
        )
        assert ps.elapsed_seconds == 15.5  # noqa: PLR2004


class TestResolvePhase:
    def test_known_tool(self):
        assert resolve_phase("create_file_manifest") == AnalysisPhase.FOUNDATION

    def test_unknown_tool(self):
        assert resolve_phase("some_random_tool") is None
