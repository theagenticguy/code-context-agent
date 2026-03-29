"""Index metadata model for pre-computed analysis artifacts."""

from __future__ import annotations

from typing import Any

from .base import FrozenModel


class IndexMetadata(FrozenModel):
    """Metadata produced by the deterministic indexer.

    Captures repository characteristics and pre-computed analysis data
    so the coordinator agent can make informed dispatch decisions without
    re-running discovery.
    """

    file_count: int
    languages: dict[str, int]
    frameworks: list[str]
    graph_stats: dict[str, Any]
    top_entry_points: list[dict[str, Any]]
    top_hotspots: list[dict[str, Any]]
    has_signatures: bool
    has_orientation: bool
    indexed_at: str
