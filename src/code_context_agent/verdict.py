"""Deterministic change verdict engine.

Analyzes a git diff against pre-computed codebase context (risk profiles,
GitNexus structural data, git history) and produces a machine-readable
verdict. Designed for CI/CD consumption with <60s latency — no LLM calls.

Pipeline:
    1. git diff → changed files
    2. gitnexus cypher → map files to symbols + communities
    3. gitnexus impact → blast radius for high-risk symbols
    4. cross-reference with risk_profile from analysis_result.json
    5. aggregate signals → composite verdict + confidence
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from pathlib import Path

from loguru import logger

from code_context_agent.config import DEFAULT_OUTPUT_DIR
from code_context_agent.models.output import (
    ChangeVerdict,
    DecisionBoundary,
    IndexFreshness,
    ReviewerRecommendation,
    VerdictResponse,
    VerdictSignal,
)

# ---------------------------------------------------------------------------
# Verdict tier ordering (lower index = less restrictive)
# ---------------------------------------------------------------------------

_VERDICT_TIERS = ["auto_merge", "single_review", "dual_review", "expert_review", "block"]
_TIER_EXIT_CODES = {
    "auto_merge": 0,
    "single_review": 1,
    "dual_review": 1,
    "expert_review": 2,
    "block": 3,
}

# Blast radius thresholds for severity classification
_BLAST_BLOCK_THRESHOLD = 50
_BLAST_ESCALATION_THRESHOLD = 20
_BLAST_WARNING_THRESHOLD = 5

# Community count thresholds
_CROSS_COMMUNITY_ESCALATION = 3

# Freshness thresholds (hours)
_FRESHNESS_OUTDATED_HOURS = 168  # 7 days
_FRESHNESS_STALE_HOURS = 48  # 2 days

# Label thresholds
_HIGH_BLAST_RADIUS = 20
_CROSS_CUTTING_COMMUNITIES = 2

# Boundary distance display threshold
_BOUNDARY_DISPLAY_THRESHOLD = 0.3


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_verdict(
    repo_path: Path,
    base_ref: str = "main",
    head_ref: str = "HEAD",
) -> VerdictResponse:
    """Compute a change verdict for the diff between base_ref and head_ref.

    Args:
        repo_path: Absolute path to the repository root.
        base_ref: Git ref for the base (e.g., 'main', 'origin/main').
        head_ref: Git ref for the head (e.g., 'HEAD', branch name).

    Returns:
        VerdictResponse with verdict, signals, and CI-actionable fields.
    """
    repo = repo_path.resolve()
    agent_dir = repo / DEFAULT_OUTPUT_DIR

    # Step 1: Get changed files
    changed_files = _get_changed_files(repo, base_ref, head_ref)
    if not changed_files:
        return _empty_verdict("No files changed between base and head.")

    # Step 2: Load pre-computed context
    analysis_result = _load_json(agent_dir / "analysis_result.json")
    heuristic = _load_json(agent_dir / "heuristic_summary.json")

    # Step 3: Compute index freshness
    freshness = _compute_freshness(agent_dir, repo, base_ref)

    # Step 4: Map files to symbols and communities via GitNexus
    symbol_data = _map_files_to_symbols(repo, changed_files, heuristic)

    # Step 5: Get blast radius for changed symbols
    impact_data = _get_impact(repo, symbol_data.get("symbols", []), heuristic)

    # Step 6: Aggregate signals and produce verdict
    risk_profile = analysis_result.get("risk_profile") if analysis_result else None
    return _assemble_verdict(
        repo=repo,
        base_ref=base_ref,
        head_ref=head_ref,
        changed_files=changed_files,
        symbol_data=symbol_data,
        impact_data=impact_data,
        risk_profile=risk_profile,
        heuristic=heuristic,
        analysis_result=analysis_result,
        freshness=freshness,
    )


def _assemble_verdict(
    *,
    repo: Path,
    base_ref: str,
    head_ref: str,
    changed_files: list[str],
    symbol_data: dict[str, Any],
    impact_data: dict[str, Any],
    risk_profile: dict[str, Any] | None,
    heuristic: dict[str, Any] | None,
    analysis_result: dict[str, Any] | None,
    freshness: IndexFreshness,
) -> VerdictResponse:
    """Aggregate signals and assemble the final VerdictResponse."""
    all_signals: list[VerdictSignal] = []
    reasoning: list[str] = [f"1. Diff: {len(changed_files)} files changed ({base_ref}..{head_ref})"]

    # Blast radius signals
    total_blast = impact_data.get("total_upstream", 0)
    _add_blast_signals(all_signals, reasoning, total_blast, impact_data)

    # Cross-community signals
    communities = symbol_data.get("communities", [])
    _add_community_signals(all_signals, reasoning, communities)

    # Risk profile matching
    affected_areas = _match_risk_areas(risk_profile, changed_files, communities)
    for area_info in affected_areas:
        area = area_info["area"]
        risk_level = area_info.get("risk_level", "medium")
        review_rec = area_info.get("review_recommendation", "single_review")
        reasoning.append(f"4. Area '{area}': risk={risk_level}, rec={review_rec}")

    # Security + git signals
    for sig in _check_security(heuristic, changed_files):
        all_signals.append(sig)
        reasoning.append(f"5. Security: {sig.description}")
    git_signals = _check_git_signals(heuristic, changed_files)
    for sig in git_signals:
        all_signals.append(sig)
        reasoning.append(f"6. Git: {sig.description}")

    # Temporal trend signals
    for sig in _check_temporal_trends(repo, communities):
        all_signals.append(sig)
        reasoning.append(f"7. Trend: {sig.description}")

    # Pattern consistency signals
    for sig in _check_pattern_consistency(repo):
        all_signals.append(sig)
        reasoning.append(f"8. Pattern: {sig.description}")

    # Composite verdict
    verdict_tier = _compute_tier(all_signals, affected_areas, freshness)
    confidence = _compute_confidence(all_signals, analysis_result is not None, freshness)

    # Decision boundary
    tier_idx = _VERDICT_TIERS.index(verdict_tier)
    next_tier = _VERDICT_TIERS[tier_idx + 1] if tier_idx < len(_VERDICT_TIERS) - 1 else verdict_tier
    boundary = DecisionBoundary(
        current_verdict=verdict_tier,
        next_higher_verdict=next_tier,
        distance=_compute_boundary_distance(all_signals, verdict_tier),
        escalation_triggers=_escalation_triggers(all_signals, verdict_tier),
        de_escalation_triggers=_de_escalation_triggers(all_signals, verdict_tier),
    )

    reasoning.append(
        f"VERDICT: {verdict_tier} (confidence={confidence:.2f}, "
        f"freshness={freshness.freshness}, penalty={freshness.confidence_penalty})",
    )

    change_verdict = ChangeVerdict(
        verdict=verdict_tier,
        confidence=confidence,
        affected_symbols=symbol_data.get("symbols", [])[:50],
        affected_communities=communities,
        affected_processes=impact_data.get("processes", []),
        blast_radius=total_blast,
        signals=all_signals,
        escalation_reasons=[s.description for s in all_signals if s.severity in ("escalation", "block")],
        reasoning_chain=reasoning,
        decision_boundary=boundary,
        recommended_reviewers=_recommend_reviewers(repo, changed_files, impact_data, git_signals),
        files_changed=changed_files,
    )

    return VerdictResponse(
        verdict=change_verdict,
        index_freshness=freshness,
        exit_code=_TIER_EXIT_CODES.get(verdict_tier, 4),
        should_block=verdict_tier == "block",
        review_comment_markdown=_render_review_comment(change_verdict, freshness),
        github_labels=_suggest_labels(change_verdict),
    )


def _add_blast_signals(
    signals: list[VerdictSignal],
    reasoning: list[str],
    total_blast: int,
    impact_data: dict[str, Any],
) -> None:
    """Add blast radius signals if applicable."""
    if total_blast <= 0:
        return
    reasoning.append(f"2. Blast radius: {total_blast} total upstream dependents")
    if total_blast > _BLAST_BLOCK_THRESHOLD:
        severity = "block"
    elif total_blast > _BLAST_ESCALATION_THRESHOLD:
        severity = "escalation"
    elif total_blast > _BLAST_WARNING_THRESHOLD:
        severity = "warning"
    else:
        severity = "info"
    symbol_count = len(impact_data.get("symbols", []))
    signals.append(
        VerdictSignal(
            signal_type="blast_radius",
            severity=severity,
            description=f"{total_blast} upstream dependents across {symbol_count} changed symbols",
            source="gitnexus_impact",
            weight=min(1.0, total_blast / _BLAST_BLOCK_THRESHOLD),
        ),
    )


def _add_community_signals(
    signals: list[VerdictSignal],
    reasoning: list[str],
    communities: list[str],
) -> None:
    """Add cross-community signals if applicable."""
    if len(communities) > 1:
        names = ", ".join(communities[:5])
        reasoning.append(f"3. Cross-community: spans {len(communities)} communities ({names})")
        severity = "warning" if len(communities) <= _CROSS_COMMUNITY_ESCALATION else "escalation"
        signals.append(
            VerdictSignal(
                signal_type="cross_community",
                severity=severity,
                description=f"Changes span {len(communities)} GitNexus communities: {names}",
                source="gitnexus_cypher",
                weight=min(1.0, len(communities) / 5),
            ),
        )
    elif communities:
        reasoning.append(f"3. Single community: {communities[0]}")


# ---------------------------------------------------------------------------
# Git diff
# ---------------------------------------------------------------------------


def _get_changed_files(repo: Path, base_ref: str, head_ref: str) -> list[str]:
    """Get list of files changed between base_ref and head_ref."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Try merge-base form for diverged branches
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=30,
            )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"git diff failed: {e}")
    return []


# ---------------------------------------------------------------------------
# GitNexus integration
# ---------------------------------------------------------------------------


def _map_files_to_symbols(
    repo: Path,
    changed_files: list[str],
    heuristic: dict[str, Any] | None,
) -> dict[str, Any]:
    """Map changed files to symbols and communities via GitNexus cypher."""
    result: dict[str, Any] = {"symbols": [], "communities": []}

    gitnexus_info = (heuristic or {}).get("gitnexus", {})
    if not gitnexus_info.get("indexed"):
        return result

    if shutil.which("gitnexus") is None:
        return result

    repo_name = gitnexus_info.get("repo_name", repo.name)

    # Query symbols in changed files
    file_list = ", ".join(f'"{f}"' for f in changed_files[:100])
    cypher = (
        f"MATCH (s:Symbol) WHERE s.file IN [{file_list}] RETURN s.name, s.file, s.community ORDER BY s.name LIMIT 200"
    )

    try:
        cypher_result = subprocess.run(
            ["gitnexus", "cypher", "--repo", repo_name, cypher],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if cypher_result.returncode == 0:
            data = json.loads(cypher_result.stdout)
            markdown = data.get("markdown", "")
            symbols: list[str] = []
            communities: set[str] = set()
            for raw_line in markdown.split("\n"):
                line = raw_line.strip()
                if not line or line.startswith("| ---") or line.startswith("| s."):
                    continue
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 1:
                    symbols.append(parts[0])
                if len(parts) >= 3 and parts[2]:  # noqa: PLR2004
                    communities.add(parts[2])
            result["symbols"] = symbols
            result["communities"] = sorted(communities)
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.debug(f"GitNexus cypher query failed: {e}")

    return result


def _get_impact(
    repo: Path,
    symbols: list[str],
    heuristic: dict[str, Any] | None,
) -> dict[str, Any]:
    """Get blast radius for changed symbols via GitNexus impact."""
    result: dict[str, Any] = {"total_upstream": 0, "symbols": [], "processes": []}

    gitnexus_info = (heuristic or {}).get("gitnexus", {})
    if not gitnexus_info.get("indexed") or shutil.which("gitnexus") is None:
        return result

    repo_name = gitnexus_info.get("repo_name", repo.name)

    # Only check impact for the first N symbols to stay within timeout
    symbols_to_check = symbols[:10]
    total_upstream = 0
    all_processes: set[str] = set()

    for symbol in symbols_to_check:
        try:
            impact_result = subprocess.run(
                ["gitnexus", "impact", "--repo", repo_name, "--direction", "upstream", symbol],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if impact_result.returncode == 0:
                data = json.loads(impact_result.stdout)
                upstream = data.get("upstream_count", 0)
                if isinstance(upstream, int):
                    total_upstream += upstream
                processes = data.get("affected_processes", [])
                if isinstance(processes, list):
                    for p in processes:
                        if isinstance(p, str):
                            all_processes.add(p)
                        elif isinstance(p, dict):
                            all_processes.add(p.get("name", str(p)))
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
            logger.debug(f"GitNexus impact failed for {symbol}: {e}")

    result["total_upstream"] = total_upstream
    result["symbols"] = symbols_to_check
    result["processes"] = sorted(all_processes)
    return result


# ---------------------------------------------------------------------------
# Risk profile matching
# ---------------------------------------------------------------------------


def _match_risk_areas(
    risk_profile: dict[str, Any] | None,
    changed_files: list[str],
    communities: list[str],
) -> list[dict[str, Any]]:
    """Match changed files/communities against pre-computed risk area profiles."""
    if not risk_profile:
        return []

    areas = risk_profile.get("areas", [])
    if not areas:
        return []

    matched: list[dict[str, Any]] = []
    community_set = {c.lower() for c in communities}

    for area in areas:
        area_name = area.get("area", "").lower()
        # Match by community name overlap
        if area_name in community_set:
            matched.append(area)
            continue
        # Match by file path heuristic (area name appears in path)
        if any(area_name in f.lower() for f in changed_files):
            matched.append(area)

    return matched


# ---------------------------------------------------------------------------
# Security signal detection
# ---------------------------------------------------------------------------


def _check_security(
    heuristic: dict[str, Any] | None,
    _changed_files: list[str],
) -> list[VerdictSignal]:
    """Check if changed files have known security findings."""
    signals: list[VerdictSignal] = []
    if not heuristic:
        return signals

    health = heuristic.get("health", {})
    semgrep = health.get("semgrep_findings", {})

    critical = semgrep.get("critical", 0)
    high = semgrep.get("high", 0)

    if critical > 0:
        signals.append(
            VerdictSignal(
                signal_type="security_finding",
                severity="block",
                description=f"Repository has {critical} critical semgrep finding(s) — changed files may be affected",
                source="semgrep",
                weight=1.0,
            ),
        )
    elif high > 0:
        signals.append(
            VerdictSignal(
                signal_type="security_finding",
                severity="escalation",
                description=f"Repository has {high} high-severity semgrep finding(s)",
                source="semgrep",
                weight=0.7,
            ),
        )

    return signals


# ---------------------------------------------------------------------------
# Git history signals
# ---------------------------------------------------------------------------


def _check_git_signals(
    heuristic: dict[str, Any] | None,
    changed_files: list[str],
) -> list[VerdictSignal]:
    """Check git history signals (churn, bus factor) for changed files."""
    signals: list[VerdictSignal] = []
    if not heuristic:
        return signals

    git = heuristic.get("git", {})

    # Check if any changed files are top hotspots
    hotspots = git.get("top_hotspot_files", [])
    hotspot_set = {h.get("path", "") if isinstance(h, dict) else str(h) for h in hotspots[:10]}
    hot_files = [f for f in changed_files if f in hotspot_set]
    if hot_files:
        signals.append(
            VerdictSignal(
                signal_type="churn_rate",
                severity="warning",
                description=f"{len(hot_files)} changed file(s) are top-10 hotspots: {', '.join(hot_files[:3])}",
                source="git_hotspots",
                weight=min(1.0, len(hot_files) / 5),
            ),
        )

    # Check bus factor risks
    bus_risks = heuristic.get("complexity", {}).get("bus_factor_risks", [])
    if bus_risks:
        affected_bus = [
            r
            for r in bus_risks
            if any(f.startswith(r if isinstance(r, str) else r.get("path", "")) for f in changed_files)
        ]
        if affected_bus:
            signals.append(
                VerdictSignal(
                    signal_type="bus_factor",
                    severity="escalation",
                    description=f"Changes touch {len(affected_bus)} area(s) with bus factor risk (single contributor)",
                    source="git_contributors",
                    weight=0.6,
                ),
            )

    return signals


# ---------------------------------------------------------------------------
# Temporal trend signals
# ---------------------------------------------------------------------------


def _check_temporal_trends(repo: Path, communities: list[str]) -> list[VerdictSignal]:
    """Check if affected communities have degrading risk trends."""
    signals: list[VerdictSignal] = []

    try:
        from code_context_agent.temporal import compute_risk_trends

        trends = compute_risk_trends(repo)
    except Exception:  # noqa: BLE001
        return signals

    community_set = {c.lower() for c in communities}

    for trend in trends:
        area_lower = trend.area.lower()
        if area_lower not in community_set and not any(area_lower in c for c in community_set):
            continue

        if trend.risk_trend == "accelerating_risk":
            signals.append(
                VerdictSignal(
                    signal_type="complexity_spike",
                    severity="escalation",
                    description=f"Area '{trend.area}' has accelerating risk trend "
                    f"(projected {trend.projected_risk_30d} in 30d)",
                    source="temporal_risk",
                    weight=0.7,
                ),
            )
        elif trend.risk_trend == "degrading":
            signals.append(
                VerdictSignal(
                    signal_type="complexity_spike",
                    severity="warning",
                    description=f"Area '{trend.area}' has degrading risk trend (currently {trend.current_risk})",
                    source="temporal_risk",
                    weight=0.4,
                ),
            )

    return signals


# ---------------------------------------------------------------------------
# Pattern consistency signals
# ---------------------------------------------------------------------------


def _check_pattern_consistency(repo: Path) -> list[VerdictSignal]:
    """Check if a patterns.json exists and flag known violations."""
    signals: list[VerdictSignal] = []
    patterns_path = repo / DEFAULT_OUTPUT_DIR / "patterns.json"

    if not patterns_path.exists():
        return signals

    try:
        data = json.loads(patterns_path.read_text())
    except (json.JSONDecodeError, OSError):
        return signals

    # If patterns exist with known violations, flag them
    patterns = data if isinstance(data, list) else data.get("patterns", [])
    total_violations = sum(p.get("violation_count", 0) for p in patterns if isinstance(p, dict))

    if total_violations > 0:
        signals.append(
            VerdictSignal(
                signal_type="pattern_violation",
                severity="warning",
                description=f"Codebase has {total_violations} known pattern violation(s)",
                source="patterns.json",
                weight=min(1.0, total_violations / 10),
            ),
        )

    return signals


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------


VerdictTier = Literal["auto_merge", "single_review", "dual_review", "expert_review", "block"]


def _compute_tier(
    signals: list[VerdictSignal],
    affected_areas: list[dict[str, Any]],
    freshness: IndexFreshness,
) -> VerdictTier:
    """Compute the verdict tier from accumulated signals and risk areas."""
    # Start at auto_merge and escalate
    tier_idx = 0

    # Any blocking signal → block
    if any(s.severity == "block" for s in signals):
        return "block"

    # Escalation signals push up by 1 tier each
    escalation_count = sum(1 for s in signals if s.severity == "escalation")
    tier_idx += escalation_count

    # Warning signals push up by 0.5 tier each (rounded)
    warning_count = sum(1 for s in signals if s.severity == "warning")
    tier_idx += (warning_count + 1) // 2

    # Risk area recommendations can pull the tier up
    for area in affected_areas:
        rec = area.get("review_recommendation", "single_review")
        if rec in _VERDICT_TIERS:
            area_idx = _VERDICT_TIERS.index(rec)
            tier_idx = max(tier_idx, area_idx)

    # Stale data → at least single_review
    if freshness.freshness == "outdated":
        tier_idx = max(tier_idx, 1)

    clamped = min(tier_idx, len(_VERDICT_TIERS) - 1)
    return cast("VerdictTier", _VERDICT_TIERS[clamped])


def _compute_confidence(
    signals: list[VerdictSignal],
    has_analysis: bool,
    freshness: IndexFreshness,
) -> float:
    """Compute calibrated confidence score."""
    confidence = 0.8 if has_analysis else 0.4

    # GitNexus data available boosts confidence
    gitnexus_signals = [s for s in signals if "gitnexus" in s.source]
    if gitnexus_signals:
        confidence += 0.1

    # More signals = more information = slightly higher confidence
    if len(signals) >= 3:  # noqa: PLR2004
        confidence += 0.05

    # Freshness penalty
    confidence -= freshness.confidence_penalty

    return max(0.1, min(1.0, confidence))


def _compute_boundary_distance(signals: list[VerdictSignal], current_tier: str) -> float:
    """Estimate how close the verdict is to flipping to the next tier."""
    # Heuristic: count signals near the escalation threshold
    escalation_signals = [s for s in signals if s.severity in ("warning", "escalation")]
    if not escalation_signals:
        return 0.0  # Firmly in current tier

    # More warning signals without escalation = closer to flipping
    warnings_only = [s for s in escalation_signals if s.severity == "warning"]
    if current_tier == "auto_merge" and warnings_only:
        return min(1.0, len(warnings_only) * 0.3)

    return min(1.0, sum(s.weight for s in escalation_signals) / 3)


def _escalation_triggers(_signals: list[VerdictSignal], current_tier: str) -> list[str]:
    """Identify what would escalate the verdict."""
    triggers: list[str] = []
    if current_tier == "auto_merge":
        triggers.append("Any untested code path would trigger single_review")
        triggers.append("Security finding in changed files would trigger block")
    elif current_tier in ("single_review", "dual_review"):
        triggers.append("Additional bus factor risk would escalate")
        triggers.append(f"Blast radius > {_BLAST_BLOCK_THRESHOLD} would trigger expert_review")
    return triggers


def _de_escalation_triggers(signals: list[VerdictSignal], current_tier: str) -> list[str]:
    """Identify what would de-escalate the verdict."""
    triggers: list[str] = []
    if current_tier == "single_review":
        bus_signals = [s for s in signals if s.signal_type == "bus_factor"]
        if bus_signals:
            triggers.append("Adding a second contributor to bus-factor areas")
        churn_signals = [s for s in signals if s.signal_type == "churn_rate"]
        if churn_signals:
            triggers.append("Adding tests for hotspot files")
    elif current_tier in ("dual_review", "expert_review"):
        triggers.append("Reducing blast radius by narrowing the change scope")
        triggers.append("Adding test coverage for changed code paths")
    return triggers


# ---------------------------------------------------------------------------
# Reviewer recommendations
# ---------------------------------------------------------------------------


def _recommend_reviewers(
    repo: Path,
    changed_files: list[str],
    _impact_data: dict[str, Any],
    git_signals: list[VerdictSignal],
) -> list[ReviewerRecommendation]:
    """Recommend reviewers based on git blame and impact data."""
    reviewers: list[ReviewerRecommendation] = []

    # Get top contributor from git blame for changed files
    contributors: dict[str, int] = {}
    for file_path in changed_files[:5]:
        try:
            result = subprocess.run(
                ["git", "log", "-n10", "--format=%aN <%aE>", "--", file_path],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for raw in result.stdout.strip().splitlines():
                    author = raw.strip()
                    if author:
                        contributors[author] = contributors.get(author, 0) + 1
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            continue  # Skip files where git log fails

    # Sort by contribution count, take top 3
    sorted_contributors = sorted(contributors.items(), key=lambda x: x[1], reverse=True)
    for identity, count in sorted_contributors[:3]:
        reviewers.append(
            ReviewerRecommendation(
                identity=identity,
                reason="recent_contributor" if count >= 3 else "area_expert",  # noqa: PLR2004
                confidence=min(0.9, count / 10),
            ),
        )

    # If bus factor signals, flag for mitigation (skip if already recommended)
    seen_identities = {r.identity for r in reviewers}
    bus_signals = [s for s in git_signals if s.signal_type == "bus_factor"]
    if bus_signals and sorted_contributors:
        primary = sorted_contributors[0][0]
        if primary in seen_identities:
            return reviewers
        reviewers.append(
            ReviewerRecommendation(
                identity=primary,
                reason="bus_factor_mitigation",
                confidence=0.7,
            ),
        )

    return reviewers


# ---------------------------------------------------------------------------
# Index freshness
# ---------------------------------------------------------------------------


def _compute_freshness(agent_dir: Path, repo: Path, base_ref: str) -> IndexFreshness:
    """Compute how fresh the pre-computed analysis is."""
    result_path = agent_dir / "analysis_result.json"
    heuristic_path = agent_dir / "heuristic_summary.json"

    last_full: str | None = None
    last_incremental: str | None = None
    freshness = "current"
    penalty = 0.0

    # Check analysis_result.json mtime
    if result_path.exists():
        mtime = datetime.fromtimestamp(result_path.stat().st_mtime, tz=UTC)
        last_full = mtime.isoformat()
        age_hours = (datetime.now(tz=UTC) - mtime).total_seconds() / 3600
        if age_hours > _FRESHNESS_OUTDATED_HOURS:
            freshness = "outdated"
            penalty = 0.3
        elif age_hours > _FRESHNESS_STALE_HOURS:
            freshness = "stale"
            penalty = 0.15

    if heuristic_path.exists():
        mtime = datetime.fromtimestamp(heuristic_path.stat().st_mtime, tz=UTC)
        last_incremental = mtime.isoformat()

    # Count commits since last full analysis
    commits_since = 0
    if result_path.exists():
        try:
            mtime_epoch = int(result_path.stat().st_mtime)
            count_result = subprocess.run(
                ["git", "rev-list", "--count", f"--since={mtime_epoch}", base_ref],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if count_result.returncode == 0:
                commits_since = int(count_result.stdout.strip())
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError, OSError):
            pass  # Commit count is best-effort; default to 0

    return IndexFreshness(
        last_full_analysis=last_full,
        last_incremental_index=last_incremental,
        commits_since_last_full=commits_since,
        freshness=freshness,
        confidence_penalty=penalty,
    )


# ---------------------------------------------------------------------------
# Review comment rendering
# ---------------------------------------------------------------------------


_SEVERITY_ICONS = {
    "info": "(i)",
    "warning": "(!)",
    "escalation": "(!!)",
    "block": "[BLOCK]",
}


def _render_review_comment(verdict: ChangeVerdict, freshness: IndexFreshness) -> str:
    """Render a markdown PR comment from the verdict."""
    lines: list[str] = []
    lines.append(f"## Code Context Verdict: `{verdict.verdict}`")
    lines.append("")
    lines.append(
        f"**Confidence:** {verdict.confidence:.0%} | **Data freshness:** {freshness.freshness}",
    )
    if freshness.freshness != "current":
        lines.append(
            f"> **Warning:** Analysis data is {freshness.freshness}. Consider re-running `code-context-agent index`.",
        )
    lines.append("")
    community_count = len(verdict.affected_communities)
    lines.append(
        f"**{len(verdict.files_changed)}** files changed "
        f"| **{verdict.blast_radius}** upstream dependents "
        f"| **{community_count}** communities affected",
    )
    lines.append("")
    _render_signals_section(lines, verdict)
    _render_boundary_section(lines, verdict)
    lines.append("---")
    lines.append(
        "*Generated by [code-context-agent](https://github.com/theagenticguy/code-context-agent)*",
    )
    return "\n".join(lines)


def _render_signals_section(lines: list[str], verdict: ChangeVerdict) -> None:
    """Append signal, escalation, and reviewer sections to *lines*."""
    if verdict.signals:
        lines.append("### Signals")
        lines.append("")
        for signal in verdict.signals:
            icon = _SEVERITY_ICONS.get(signal.severity, "-")
            lines.append(f"- {icon} **{signal.signal_type}**: {signal.description}")
        lines.append("")
    if verdict.escalation_reasons:
        lines.append("### Why this verdict")
        lines.append("")
        for reason in verdict.escalation_reasons:
            lines.append(f"- {reason}")
        lines.append("")
    if verdict.recommended_reviewers:
        lines.append("### Recommended reviewers")
        lines.append("")
        for reviewer in verdict.recommended_reviewers:
            lines.append(f"- {reviewer.identity} ({reviewer.reason})")
        lines.append("")


def _render_boundary_section(lines: list[str], verdict: ChangeVerdict) -> None:
    """Append decision-boundary section to *lines* if borderline."""
    boundary = verdict.decision_boundary
    if not boundary or boundary.distance <= _BOUNDARY_DISPLAY_THRESHOLD:
        return
    lines.append("### Borderline verdict")
    lines.append("")
    lines.append(
        f"This verdict is **{boundary.distance:.0%}** of the way to `{boundary.next_higher_verdict}`.",
    )
    if boundary.de_escalation_triggers:
        lines.append("")
        lines.append("To de-escalate:")
        for trigger in boundary.de_escalation_triggers:
            lines.append(f"- {trigger}")
    lines.append("")


def _suggest_labels(verdict: ChangeVerdict) -> list[str]:
    """Suggest GitHub labels based on the verdict."""
    labels: list[str] = []

    if verdict.verdict == "auto_merge":
        labels.append("auto-approvable")
    elif verdict.verdict == "block":
        labels.append("blocked")

    if any(s.signal_type == "security_finding" for s in verdict.signals):
        labels.append("needs-security-review")

    if any(s.signal_type == "bus_factor" for s in verdict.signals):
        labels.append("bus-factor-risk")

    if verdict.blast_radius > _HIGH_BLAST_RADIUS:
        labels.append("high-blast-radius")

    if len(verdict.affected_communities) > _CROSS_CUTTING_COMMUNITIES:
        labels.append("cross-cutting")

    return labels


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None on missing or parse error."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _empty_verdict(message: str) -> VerdictResponse:
    """Return an empty auto_merge verdict for no-change scenarios."""
    return VerdictResponse(
        verdict=ChangeVerdict(
            verdict="auto_merge",
            confidence=1.0,
            reasoning_chain=[message],
        ),
        exit_code=0,
        should_block=False,
        review_comment_markdown=f"## Code Context Verdict: `auto_merge`\n\n{message}",
    )
