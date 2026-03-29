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
    """Ordered analysis phases (1-5) for the coordinator pipeline."""

    INDEXING = 1
    TEAM_PLANNING = 2
    TEAM_EXECUTION = 3
    CONSOLIDATION = 4
    BUNDLE_GENERATION = 5


TOOL_PHASE_MAP: dict[str, AnalysisPhase] = {
    # Phase 2: Team Planning (coordinator reads heuristic summary)
    "read_heuristic_summary": AnalysisPhase.TEAM_PLANNING,
    # Phase 3: Team Execution (coordinator dispatches teams + all team agent tools)
    "dispatch_team": AnalysisPhase.TEAM_EXECUTION,
    # -- Discovery tools (used by team agents) --
    "create_file_manifest": AnalysisPhase.TEAM_EXECUTION,
    "repomix_orientation": AnalysisPhase.TEAM_EXECUTION,
    "repomix_compressed_signatures": AnalysisPhase.TEAM_EXECUTION,
    "repomix_bundle": AnalysisPhase.TEAM_EXECUTION,
    "repomix_bundle_with_context": AnalysisPhase.TEAM_EXECUTION,
    "repomix_split_bundle": AnalysisPhase.TEAM_EXECUTION,
    "repomix_json_export": AnalysisPhase.TEAM_EXECUTION,
    "read_file_bounded": AnalysisPhase.TEAM_EXECUTION,
    "write_file_list": AnalysisPhase.TEAM_EXECUTION,
    "write_file": AnalysisPhase.TEAM_EXECUTION,
    "rg_search": AnalysisPhase.TEAM_EXECUTION,
    "bm25_search": AnalysisPhase.TEAM_EXECUTION,
    "shell": AnalysisPhase.TEAM_EXECUTION,
    "detect_clones": AnalysisPhase.TEAM_EXECUTION,
    # -- LSP tools (used by team agents) --
    "lsp_start": AnalysisPhase.TEAM_EXECUTION,
    "lsp_document_symbols": AnalysisPhase.TEAM_EXECUTION,
    "lsp_references": AnalysisPhase.TEAM_EXECUTION,
    "lsp_definition": AnalysisPhase.TEAM_EXECUTION,
    "lsp_hover": AnalysisPhase.TEAM_EXECUTION,
    "lsp_workspace_symbols": AnalysisPhase.TEAM_EXECUTION,
    "lsp_diagnostics": AnalysisPhase.TEAM_EXECUTION,
    "lsp_shutdown": AnalysisPhase.TEAM_EXECUTION,
    # -- AST-grep tools (used by team agents) --
    "astgrep_scan": AnalysisPhase.TEAM_EXECUTION,
    "astgrep_scan_rule_pack": AnalysisPhase.TEAM_EXECUTION,
    "astgrep_inline_rule": AnalysisPhase.TEAM_EXECUTION,
    # -- Git tools (used by team agents) --
    "git_hotspots": AnalysisPhase.TEAM_EXECUTION,
    "git_files_changed_together": AnalysisPhase.TEAM_EXECUTION,
    "git_blame_summary": AnalysisPhase.TEAM_EXECUTION,
    "git_file_history": AnalysisPhase.TEAM_EXECUTION,
    "git_contributors": AnalysisPhase.TEAM_EXECUTION,
    "git_recent_commits": AnalysisPhase.TEAM_EXECUTION,
    "git_diff_file": AnalysisPhase.TEAM_EXECUTION,
    # -- Graph tools (used by team agents) --
    "code_graph_create": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_ingest_lsp": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_ingest_astgrep": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_ingest_rg": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_ingest_inheritance": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_ingest_tests": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_ingest_git": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_ingest_clones": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_analyze": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_explore": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_export": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_save": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_load": AnalysisPhase.TEAM_EXECUTION,
    "code_graph_stats": AnalysisPhase.TEAM_EXECUTION,
    # Phase 4: Consolidation (coordinator reads team findings)
    "read_team_findings": AnalysisPhase.CONSOLIDATION,
    # Phase 5: Bundle Generation (coordinator writes bundles)
    "write_bundle": AnalysisPhase.BUNDLE_GENERATION,
}

PHASE_NAMES: dict[AnalysisPhase, str] = {
    AnalysisPhase.INDEXING: "Indexing",
    AnalysisPhase.TEAM_PLANNING: "Team Planning",
    AnalysisPhase.TEAM_EXECUTION: "Team Execution",
    AnalysisPhase.CONSOLIDATION: "Consolidation",
    AnalysisPhase.BUNDLE_GENERATION: "Bundle Generation",
}

PHASE_DESCRIPTIONS: dict[AnalysisPhase, str] = {
    AnalysisPhase.INDEXING: "Deterministic code indexing (no LLM)",
    AnalysisPhase.TEAM_PLANNING: "Reading heuristic summary, planning teams",
    AnalysisPhase.TEAM_EXECUTION: "Parallel specialist teams analyzing code",
    AnalysisPhase.CONSOLIDATION: "Reading and cross-referencing team findings",
    AnalysisPhase.BUNDLE_GENERATION: "Writing targeted bundle files",
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
