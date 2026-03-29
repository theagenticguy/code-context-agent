"""Tests for AgentDisplayState phase/discovery/team extensions."""

from __future__ import annotations

from code_context_agent.consumer.phases import AnalysisPhase, DiscoveryEvent, DiscoveryEventKind
from code_context_agent.consumer.state import AgentDisplayState


class TestAgentDisplayStatePhases:
    def test_advance_phase_from_none(self):
        state = AgentDisplayState()
        state.advance_phase(AnalysisPhase.INDEXING)
        assert state.current_phase_index == 0
        assert len(state.phases) == 1
        assert state.phases[0].phase == AnalysisPhase.INDEXING

    def test_advance_phase_forward(self):
        state = AgentDisplayState()
        state.advance_phase(AnalysisPhase.INDEXING)
        state.advance_phase(AnalysisPhase.TEAM_EXECUTION)
        assert state.current_phase_index == 1
        assert state.phases[0].completed_at is not None

    def test_advance_phase_no_regress(self):
        state = AgentDisplayState()
        state.advance_phase(AnalysisPhase.TEAM_EXECUTION)
        state.advance_phase(AnalysisPhase.TEAM_PLANNING)  # Lower -- ignored
        assert state.current_phase_index == 0  # Still at TEAM_EXECUTION
        assert len(state.phases) == 1


class TestAgentDisplayStateDiscoveries:
    def test_add_discovery(self):
        state = AgentDisplayState()
        event = DiscoveryEvent(
            kind=DiscoveryEventKind.FILES_DISCOVERED,
            summary="Found 100 files",
            tool_name="t",
            timestamp=1.0,
        )
        state.add_discovery(event)
        assert len(state.discoveries) == 1

    def test_discovery_ring_buffer(self):
        state = AgentDisplayState()
        state.max_discoveries = 3
        for i in range(5):
            state.add_discovery(
                DiscoveryEvent(
                    kind=DiscoveryEventKind.FILES_DISCOVERED,
                    summary=f"Event {i}",
                    tool_name="t",
                    timestamp=float(i),
                ),
            )
        assert len(state.discoveries) == 3
        assert state.discoveries[0].summary == "Event 2"


class TestAgentDisplayStateTeams:
    def test_start_team(self):
        state = AgentDisplayState()
        state.start_team("security", "Analyze security patterns", agent_count=3)
        assert len(state.teams) == 1
        assert state.teams[0].team_id == "security"
        assert state.teams[0].mandate == "Analyze security patterns"
        assert state.teams[0].agent_count == 3
        assert state.teams[0].status == "running"
        assert state.teams[0].started_at is not None

    def test_complete_team(self):
        state = AgentDisplayState()
        state.start_team("arch", "Architecture analysis", agent_count=2)
        state.complete_team("arch", status="done")
        assert state.teams[0].status == "done"
        assert state.teams[0].duration_seconds > 0.0

    def test_complete_team_error(self):
        state = AgentDisplayState()
        state.start_team("perf", "Performance analysis", agent_count=1)
        state.complete_team("perf", status="error")
        assert state.teams[0].status == "error"

    def test_complete_unknown_team_is_noop(self):
        state = AgentDisplayState()
        state.start_team("arch", "Architecture", agent_count=2)
        state.complete_team("nonexistent")  # should not raise
        assert state.teams[0].status == "running"

    def test_reset_clears_teams(self):
        state = AgentDisplayState()
        state.start_team("arch", "Architecture", agent_count=2)
        state.reset()
        assert len(state.teams) == 0
