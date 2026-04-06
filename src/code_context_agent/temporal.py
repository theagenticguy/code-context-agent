"""Temporal risk intelligence — track risk trajectories across analysis runs.

Persists point-in-time risk snapshots after each analysis and computes
trend data (improving/degrading/stable) across snapshots. Feeds into
the verdict engine as escalation/de-escalation signals.

Storage: .code-context/history/risk_{timestamp}.json
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

from code_context_agent.config import DEFAULT_OUTPUT_DIR
from code_context_agent.models.output import (
    RiskSnapshot,
    TemporalRiskProfile,
)

if TYPE_CHECKING:
    from pathlib import Path

# Risk level ordinal for trend computation
_RISK_ORDINAL = {"low": 0, "medium": 1, "high": 2, "critical": 3}

_MAX_SNAPSHOTS = 10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def persist_risk_snapshot(repo_path: Path) -> None:
    """Save a risk snapshot from the current analysis_result.json.

    Call this after every analysis run to build temporal history.
    Creates .code-context/history/risk_{timestamp}.json.

    Args:
        repo_path: Repository root path.
    """
    agent_dir = repo_path / DEFAULT_OUTPUT_DIR
    result_path = agent_dir / "analysis_result.json"
    if not result_path.exists():
        logger.debug("No analysis_result.json — skipping snapshot")
        return

    try:
        result = json.loads(result_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read analysis_result.json: {e}")
        return

    risk_profile = result.get("risk_profile")
    if not risk_profile:
        logger.debug("No risk_profile in analysis result — skipping snapshot")
        return

    # Build per-area snapshots
    now_dt = datetime.now(tz=UTC)
    now = now_dt.isoformat()
    areas: dict[str, RiskSnapshot] = {}

    for area in risk_profile.get("areas", []):
        area_name = area.get("area", "unknown")
        areas[area_name] = RiskSnapshot(
            timestamp=now,
            risk_level=area.get("risk_level", "medium"),
            blast_radius=area.get("blast_radius", 0),
            churn_rank=area.get("churn_rank", 0),
            contributor_count=area.get("contributor_count", 0),
            test_coverage=area.get("test_coverage", "low"),
        )

    # Write snapshot
    history_dir = agent_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    ts_slug = now_dt.strftime("%Y%m%dT%H%M%SZ")
    snapshot_path = history_dir / f"risk_{ts_slug}.json"

    snapshot_data = {
        "timestamp": now,
        "overall_risk": risk_profile.get("overall_risk", "medium"),
        "areas": {name: snap.model_dump() for name, snap in areas.items()},
    }

    try:
        snapshot_path.write_text(json.dumps(snapshot_data, indent=2))
        logger.info(f"Persisted risk snapshot: {snapshot_path}")
    except OSError as e:
        logger.warning(f"Failed to write risk snapshot: {e}")


def compute_risk_trends(repo_path: Path) -> list[TemporalRiskProfile]:
    """Compute risk trends from historical snapshots.

    Reads .code-context/history/risk_*.json files and computes per-area
    trend profiles comparing the last N snapshots.

    Args:
        repo_path: Repository root path.

    Returns:
        List of TemporalRiskProfile, one per area that has history.
    """
    agent_dir = repo_path / DEFAULT_OUTPUT_DIR
    history_dir = agent_dir / "history"

    if not history_dir.exists():
        return []

    # Load snapshots sorted by timestamp
    snapshots = _load_snapshots(history_dir)
    if len(snapshots) < 2:  # noqa: PLR2004
        return _single_snapshot_profiles(snapshots)

    # Collect per-area history
    area_histories: dict[str, list[dict[str, Any]]] = {}
    for snap in snapshots:
        for area_name, area_data in snap.get("areas", {}).items():
            area_histories.setdefault(area_name, []).append(area_data)

    # Compute trends
    profiles: list[TemporalRiskProfile] = []
    for area_name, history in area_histories.items():
        recent = history[-_MAX_SNAPSHOTS:]
        profiles.append(_compute_area_trend(area_name, recent))

    return profiles


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_snapshots(history_dir: Path) -> list[dict[str, Any]]:
    """Load and sort risk snapshots by timestamp."""
    snapshots: list[dict[str, Any]] = []
    for path in sorted(history_dir.glob("risk_*.json")):
        try:
            data = json.loads(path.read_text())
            snapshots.append(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Skipping corrupt snapshot {path}: {e}")
    return snapshots


def _single_snapshot_profiles(snapshots: list[dict[str, Any]]) -> list[TemporalRiskProfile]:
    """Build profiles from a single snapshot (no trend data)."""
    if not snapshots:
        return []
    snap = snapshots[0]
    profiles: list[TemporalRiskProfile] = []
    for area_name, area_data in snap.get("areas", {}).items():
        profiles.append(
            TemporalRiskProfile(
                area=area_name,
                current_risk=area_data.get("risk_level", "medium"),
                risk_trend="stable",
                history=[RiskSnapshot(**area_data)],
            ),
        )
    return profiles


def _compute_area_trend(area_name: str, history: list[dict[str, Any]]) -> TemporalRiskProfile:
    """Compute trend for a single area from its snapshot history."""
    current = history[-1]
    previous = history[-2]

    # Risk trend
    curr_ordinal = _RISK_ORDINAL.get(current.get("risk_level", "medium"), 1)
    prev_ordinal = _RISK_ORDINAL.get(previous.get("risk_level", "medium"), 1)

    if curr_ordinal > prev_ordinal:
        # Check if it's been degrading for multiple snapshots
        degrading_streak = _count_streak(history, "risk_level", ascending=True)
        risk_trend = "accelerating_risk" if degrading_streak >= 3 else "degrading"  # noqa: PLR2004
    elif curr_ordinal < prev_ordinal:
        risk_trend = "improving"
    else:
        risk_trend = "stable"

    # Churn velocity (change in churn rank — lower rank = more churn)
    curr_churn = current.get("churn_rank", 0)
    prev_churn = previous.get("churn_rank", 0)
    churn_velocity = float(prev_churn - curr_churn)  # Positive = accelerating churn

    # Contributor trend
    curr_contrib = current.get("contributor_count", 0)
    prev_contrib = previous.get("contributor_count", 0)
    if curr_contrib > prev_contrib:
        contributor_trend = "gaining"
    elif curr_contrib < prev_contrib:
        contributor_trend = "losing"
    else:
        contributor_trend = "stable"

    # Test coverage trend
    coverage_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    curr_cov = coverage_order.get(current.get("test_coverage", "low"), 1)
    prev_cov = coverage_order.get(previous.get("test_coverage", "low"), 1)
    if curr_cov > prev_cov:
        test_coverage_trend = "improving"
    elif curr_cov < prev_cov:
        test_coverage_trend = "declining"
    else:
        test_coverage_trend = "stable"

    # Projected risk (simple linear extrapolation)
    projected_ordinal = min(3, max(0, curr_ordinal + (curr_ordinal - prev_ordinal)))
    _projected_map: dict[int, Literal["low", "medium", "high", "critical"]] = {
        0: "low",
        1: "medium",
        2: "high",
        3: "critical",
    }
    projected_risk = _projected_map.get(projected_ordinal, "medium")

    # Build snapshot models for history
    risk_history = [RiskSnapshot(**snap) for snap in history[-_MAX_SNAPSHOTS:]]

    return TemporalRiskProfile(
        area=area_name,
        current_risk=current.get("risk_level", "medium"),
        risk_trend=risk_trend,
        churn_velocity=churn_velocity,
        contributor_trend=contributor_trend,
        test_coverage_trend=test_coverage_trend,
        complexity_trend="stable",  # TODO: integrate complexity from heuristic summary
        projected_risk_30d=projected_risk,
        history=risk_history,
    )


def _count_streak(
    history: list[dict[str, Any]],
    field: str,
    *,
    ascending: bool,
) -> int:
    """Count consecutive snapshots where a field has been increasing/decreasing."""
    if len(history) < 2:  # noqa: PLR2004
        return 0

    streak = 0
    for i in range(len(history) - 1, 0, -1):
        curr_val = _RISK_ORDINAL.get(history[i].get(field, "medium"), 1)
        prev_val = _RISK_ORDINAL.get(history[i - 1].get(field, "medium"), 1)

        if (ascending and curr_val > prev_val) or (not ascending and curr_val < prev_val):
            streak += 1
        else:
            break

    return streak
