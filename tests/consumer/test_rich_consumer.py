"""Tests for RichEventConsumer v7 phase + discovery features."""

import json
import time

from code_context_agent.consumer.phases import AnalysisPhase, DiscoveryEventKind
from code_context_agent.consumer.rich_consumer import RichEventConsumer


class TestPhaseDetectionInConsumer:
    def test_tool_start_advances_phase(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        consumer._detect_phase("create_file_manifest")
        assert consumer.state.current_phase_index == 0
        assert consumer.state.phases[0].phase == AnalysisPhase.FOUNDATION

    def test_lsp_tool_advances_to_phase_3(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        consumer._detect_phase("create_file_manifest")
        consumer._detect_phase("lsp_start")
        assert consumer.state.phases[-1].phase == AnalysisPhase.SEMANTIC_DISCOVERY

    def test_unknown_tool_no_phase_change(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        consumer._detect_phase("some_unknown_tool")
        assert consumer.state.current_phase_index == -1
        assert len(consumer.state.phases) == 0


class TestDiscoveryExtraction:
    def test_file_manifest_discovery(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        result = json.dumps({"status": "success", "file_count": 847})
        event = consumer._extract_discovery("create_file_manifest", result)
        assert event is not None
        assert "847" in event.summary

    def test_error_result_no_discovery(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        result = json.dumps({"status": "error", "error": "failed"})
        event = consumer._extract_discovery("create_file_manifest", result)
        assert event is None

    def test_lsp_symbols_discovery(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        result = json.dumps({"status": "success", "count": 42})
        event = consumer._extract_discovery("lsp_document_symbols", result)
        assert event is not None
        assert "42" in event.summary

    def test_git_hotspots_discovery(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        result = json.dumps({"status": "success", "count": 15})
        event = consumer._extract_discovery("git_hotspots", result)
        assert event is not None
        assert "15" in event.summary

    def test_non_json_result_no_discovery(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        event = consumer._extract_discovery("rg_search", "not json")
        assert event is None

    def test_astgrep_scan_discovery(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        result = json.dumps({"status": "success", "match_count": 23})
        event = consumer._extract_discovery("astgrep_scan", result)
        assert event is not None
        assert "23" in event.summary
        assert event.kind == DiscoveryEventKind.PATTERNS_MATCHED

    def test_code_graph_analyze_discovery(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        result = json.dumps({"status": "success", "module_count": 8})
        event = consumer._extract_discovery("code_graph_analyze", result)
        assert event is not None
        assert "8" in event.summary
        assert event.kind == DiscoveryEventKind.MODULES_DETECTED

    def test_code_graph_create_discovery(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        result = json.dumps({"status": "success"})
        event = consumer._extract_discovery("code_graph_create", result)
        assert event is not None
        assert event.kind == DiscoveryEventKind.GRAPH_BUILT

    def test_non_string_result_no_discovery(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        event = consumer._extract_discovery("create_file_manifest", 12345)
        assert event is None

    def test_unrecognized_tool_no_discovery(self):
        consumer = RichEventConsumer()
        consumer.state.start_time = time.monotonic()
        result = json.dumps({"status": "success", "data": "something"})
        event = consumer._extract_discovery("some_random_tool", result)
        assert event is None


class TestModeBadge:
    def test_full_mode_badge(self):
        consumer = RichEventConsumer(mode="full")
        assert consumer._mode == "full"

    def test_full_plus_focus_mode_badge(self):
        consumer = RichEventConsumer(mode="full+focus")
        assert consumer._mode.startswith("full")

    def test_standard_mode_default(self):
        consumer = RichEventConsumer()
        assert consumer._mode == "standard"
