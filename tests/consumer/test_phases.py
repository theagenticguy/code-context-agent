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
        assert AnalysisPhase.INDEXING < AnalysisPhase.TEAM_EXECUTION
        assert AnalysisPhase.BUNDLE_GENERATION == 5

    def test_all_five_phases(self):
        assert len(AnalysisPhase) == 5


class TestToolPhaseMap:
    def test_read_heuristic_summary_maps_to_team_planning(self):
        assert TOOL_PHASE_MAP["read_heuristic_summary"] == AnalysisPhase.TEAM_PLANNING

    def test_dispatch_team_maps_to_team_execution(self):
        assert TOOL_PHASE_MAP["dispatch_team"] == AnalysisPhase.TEAM_EXECUTION

    def test_lsp_start_maps_to_team_execution(self):
        assert TOOL_PHASE_MAP["lsp_start"] == AnalysisPhase.TEAM_EXECUTION

    def test_astgrep_maps_to_team_execution(self):
        assert TOOL_PHASE_MAP["astgrep_scan"] == AnalysisPhase.TEAM_EXECUTION

    def test_git_maps_to_team_execution(self):
        assert TOOL_PHASE_MAP["git_hotspots"] == AnalysisPhase.TEAM_EXECUTION

    def test_graph_create_maps_to_team_execution(self):
        assert TOOL_PHASE_MAP["code_graph_create"] == AnalysisPhase.TEAM_EXECUTION

    def test_read_team_findings_maps_to_consolidation(self):
        assert TOOL_PHASE_MAP["read_team_findings"] == AnalysisPhase.CONSOLIDATION

    def test_write_bundle_maps_to_bundle_generation(self):
        assert TOOL_PHASE_MAP["write_bundle"] == AnalysisPhase.BUNDLE_GENERATION


class TestPhaseNames:
    def test_all_phases_have_names(self):
        for phase in AnalysisPhase:
            assert phase in PHASE_NAMES

    def test_all_phases_have_descriptions(self):
        for phase in AnalysisPhase:
            assert phase in PHASE_DESCRIPTIONS


class TestPhaseState:
    def test_creation(self):
        ps = PhaseState(phase=AnalysisPhase.INDEXING, name="Indexing", description="desc", started_at=100.0)
        assert ps.phase == AnalysisPhase.INDEXING
        assert ps.completed_at is None

    def test_is_complete(self):
        ps = PhaseState(phase=AnalysisPhase.INDEXING, name="Indexing", description="desc", started_at=100.0)
        assert not ps.is_complete
        ps.completed_at = 110.0
        assert ps.is_complete

    def test_elapsed_seconds(self):
        ps = PhaseState(
            phase=AnalysisPhase.INDEXING,
            name="Indexing",
            description="desc",
            started_at=100.0,
            completed_at=115.5,
        )
        assert ps.elapsed_seconds == 15.5


class TestResolvePhase:
    def test_known_tool(self):
        assert resolve_phase("dispatch_team") == AnalysisPhase.TEAM_EXECUTION

    def test_unknown_tool(self):
        assert resolve_phase("some_random_tool") is None
