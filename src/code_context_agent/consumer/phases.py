"""Analysis phase detection and discovery event models.

Maps tool names to analysis phases for the TUI progress display,
and provides models for discovery events (significant findings).
"""

from __future__ import annotations

import time
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import Field

from ..models.base import FrozenModel, StrictModel


class AnalysisPhase(IntEnum):
    """Ordered analysis phases (1-10)."""

    FOUNDATION = 1
    IDENTITY = 2
    SEMANTIC_DISCOVERY = 3
    PATTERN_DISCOVERY = 4
    GIT_HISTORY = 5
    GRAPH_ANALYSIS = 6
    BUSINESS_LOGIC = 7
    TESTS = 8
    BUNDLE = 9
    WRITE_CONTEXT = 10


TOOL_PHASE_MAP: dict[str, AnalysisPhase] = {
    # Phase 1: Foundation
    "create_file_manifest": AnalysisPhase.FOUNDATION,
    "repomix_orientation": AnalysisPhase.FOUNDATION,
    "repomix_compressed_signatures": AnalysisPhase.FOUNDATION,
    # Phase 2: Identity
    "read_file_bounded": AnalysisPhase.IDENTITY,
    # Phase 3: Semantic Discovery
    "lsp_start": AnalysisPhase.SEMANTIC_DISCOVERY,
    "lsp_document_symbols": AnalysisPhase.SEMANTIC_DISCOVERY,
    "lsp_references": AnalysisPhase.SEMANTIC_DISCOVERY,
    "lsp_definition": AnalysisPhase.SEMANTIC_DISCOVERY,
    "lsp_hover": AnalysisPhase.SEMANTIC_DISCOVERY,
    "lsp_workspace_symbols": AnalysisPhase.SEMANTIC_DISCOVERY,
    "lsp_diagnostics": AnalysisPhase.SEMANTIC_DISCOVERY,
    "lsp_shutdown": AnalysisPhase.SEMANTIC_DISCOVERY,
    # Phase 4: Pattern Discovery
    "astgrep_scan": AnalysisPhase.PATTERN_DISCOVERY,
    "astgrep_scan_rule_pack": AnalysisPhase.PATTERN_DISCOVERY,
    "astgrep_inline_rule": AnalysisPhase.PATTERN_DISCOVERY,
    # Phase 5: Git History
    "git_hotspots": AnalysisPhase.GIT_HISTORY,
    "git_files_changed_together": AnalysisPhase.GIT_HISTORY,
    "git_blame_summary": AnalysisPhase.GIT_HISTORY,
    "git_file_history": AnalysisPhase.GIT_HISTORY,
    "git_contributors": AnalysisPhase.GIT_HISTORY,
    "git_recent_commits": AnalysisPhase.GIT_HISTORY,
    "git_diff_file": AnalysisPhase.GIT_HISTORY,
    # Phase 6: Graph Analysis
    "code_graph_create": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_ingest_lsp": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_ingest_astgrep": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_ingest_rg": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_ingest_inheritance": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_ingest_tests": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_ingest_git": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_ingest_clones": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_analyze": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_explore": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_export": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_save": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_load": AnalysisPhase.GRAPH_ANALYSIS,
    "code_graph_stats": AnalysisPhase.GRAPH_ANALYSIS,
    # Phase 7: Business Logic (uses rg_search + write_file_list)
    "write_file_list": AnalysisPhase.BUSINESS_LOGIC,
    # Phase 8: Tests (uses rg_search -- detected by context)
    "detect_clones": AnalysisPhase.TESTS,
    # Phase 9: Bundle
    "repomix_bundle": AnalysisPhase.BUNDLE,
    "repomix_bundle_with_context": AnalysisPhase.BUNDLE,
    "repomix_split_bundle": AnalysisPhase.BUNDLE,
    "repomix_json_export": AnalysisPhase.BUNDLE,
    # Phase 10: Write Context
    "write_file": AnalysisPhase.WRITE_CONTEXT,
}

PHASE_NAMES: dict[AnalysisPhase, str] = {
    AnalysisPhase.FOUNDATION: "Foundation",
    AnalysisPhase.IDENTITY: "Identity",
    AnalysisPhase.SEMANTIC_DISCOVERY: "Semantic Discovery",
    AnalysisPhase.PATTERN_DISCOVERY: "Pattern Discovery",
    AnalysisPhase.GIT_HISTORY: "Git History",
    AnalysisPhase.GRAPH_ANALYSIS: "Graph Analysis",
    AnalysisPhase.BUSINESS_LOGIC: "Business Logic",
    AnalysisPhase.TESTS: "Tests & Health",
    AnalysisPhase.BUNDLE: "Bundle",
    AnalysisPhase.WRITE_CONTEXT: "Write Context",
}

PHASE_DESCRIPTIONS: dict[AnalysisPhase, str] = {
    AnalysisPhase.FOUNDATION: "File manifest, orientation, signatures",
    AnalysisPhase.IDENTITY: "Project identity and entrypoints",
    AnalysisPhase.SEMANTIC_DISCOVERY: "LSP symbols, references, definitions",
    AnalysisPhase.PATTERN_DISCOVERY: "AST-grep rule packs and patterns",
    AnalysisPhase.GIT_HISTORY: "Hotspots, coupling, blame, history",
    AnalysisPhase.GRAPH_ANALYSIS: "Code graph construction and algorithms",
    AnalysisPhase.BUSINESS_LOGIC: "Ranking and categorization",
    AnalysisPhase.TESTS: "Test coverage and code health",
    AnalysisPhase.BUNDLE: "Source code bundling",
    AnalysisPhase.WRITE_CONTEXT: "CONTEXT.md generation",
}


class DiscoveryEventKind(StrEnum):
    """Kinds of discovery events for the TUI feed."""

    FILES_DISCOVERED = "files_discovered"
    SYMBOLS_FOUND = "symbols_found"
    HOTSPOTS_IDENTIFIED = "hotspots_identified"
    MODULES_DETECTED = "modules_detected"
    PATTERNS_MATCHED = "patterns_matched"
    GRAPH_BUILT = "graph_built"


class DiscoveryEvent(FrozenModel):
    """A notable discovery made during analysis."""

    kind: DiscoveryEventKind
    summary: str = Field(description="Human-readable summary (e.g., 'Found 847 files')")
    tool_name: str = Field(description="Tool that produced this discovery")
    timestamp: float = Field(description="monotonic timestamp")
    detail: dict[str, Any] = Field(default_factory=dict, description="Optional structured detail")


class PhaseState(StrictModel):
    """Mutable state for a single analysis phase."""

    phase: AnalysisPhase
    name: str
    description: str
    started_at: float
    completed_at: float | None = None

    @property
    def is_complete(self) -> bool:
        """Whether this phase has completed."""
        return self.completed_at is not None

    @property
    def elapsed_seconds(self) -> float:
        """Seconds elapsed since phase started (or total if completed)."""
        if self.completed_at is None:
            return time.monotonic() - self.started_at
        return self.completed_at - self.started_at


def resolve_phase(tool_name: str) -> AnalysisPhase | None:
    """Resolve a tool name to its analysis phase, or None if unknown."""
    return TOOL_PHASE_MAP.get(tool_name)
