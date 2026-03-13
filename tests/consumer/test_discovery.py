"""Tests for discovery event models."""

from __future__ import annotations

from code_context_agent.consumer.phases import DiscoveryEvent, DiscoveryEventKind


class TestDiscoveryEventKind:
    def test_has_expected_kinds(self):
        assert DiscoveryEventKind.FILES_DISCOVERED
        assert DiscoveryEventKind.SYMBOLS_FOUND
        assert DiscoveryEventKind.HOTSPOTS_IDENTIFIED
        assert DiscoveryEventKind.MODULES_DETECTED
        assert DiscoveryEventKind.PATTERNS_MATCHED
        assert DiscoveryEventKind.GRAPH_BUILT


class TestDiscoveryEvent:
    def test_creation(self):
        event = DiscoveryEvent(
            kind=DiscoveryEventKind.FILES_DISCOVERED,
            summary="Found 847 files",
            tool_name="create_file_manifest",
            timestamp=100.0,
        )
        assert event.summary == "Found 847 files"
        assert event.detail == {}
