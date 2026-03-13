"""Tests for v7 AgentDisplayState phase/discovery extensions."""

from __future__ import annotations

from code_context_agent.consumer.phases import AnalysisPhase, DiscoveryEvent, DiscoveryEventKind
from code_context_agent.consumer.state import AgentDisplayState


class TestAgentDisplayStatePhases:
    def test_advance_phase_from_none(self):
        state = AgentDisplayState()
        state.advance_phase(AnalysisPhase.FOUNDATION)
        assert state.current_phase_index == 0
        assert len(state.phases) == 1
        assert state.phases[0].phase == AnalysisPhase.FOUNDATION

    def test_advance_phase_forward(self):
        state = AgentDisplayState()
        state.advance_phase(AnalysisPhase.FOUNDATION)
        state.advance_phase(AnalysisPhase.SEMANTIC_DISCOVERY)
        assert state.current_phase_index == 1
        assert state.phases[0].completed_at is not None

    def test_advance_phase_no_regress(self):
        state = AgentDisplayState()
        state.advance_phase(AnalysisPhase.GIT_HISTORY)
        state.advance_phase(AnalysisPhase.SEMANTIC_DISCOVERY)  # Lower -- ignored
        assert state.current_phase_index == 0  # Still at GIT_HISTORY
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
        assert len(state.discoveries) == 3  # noqa: PLR2004
        assert state.discoveries[0].summary == "Event 2"
