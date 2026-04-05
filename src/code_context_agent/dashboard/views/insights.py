"""Insights view: phase timing waterfall and refactoring candidate cards."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import panel as pn

    from .._data import DashboardData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _no_data(label: str) -> str:
    """Placeholder markdown when a section has no data."""
    return f"*No {label} data available.*"


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------


def _phase_timing_chart(timings: list[dict[str, Any]]) -> Any:
    """Gantt-style waterfall chart of analysis phase timings."""
    import altair as alt

    if not timings:
        return None

    rows = []
    for t in timings:
        start = t.get("start_offset_seconds", 0)
        dur = t.get("duration_seconds", 0)
        rows.append(
            {
                "name": t.get("name", f"phase-{t.get('phase', '?')}"),
                "start": start,
                "end": start + dur,
                "duration": round(dur, 1),
                "tool_count": t.get("tool_count", 0),
                "status": t.get("status", "completed"),
            },
        )

    status_domain = sorted({r["status"] for r in rows})
    status_colors = {
        "completed": "#4ade80",
        "partial": "#fbbf24",
        "failed": "#ef4444",
        "running": "#60a5fa",
    }
    range_ = [status_colors.get(s, "#6a6a86") for s in status_domain]

    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(cornerRadiusEnd=4, height=18)
        .encode(
            y=alt.Y("name:N", sort=None, title="Phase"),
            x=alt.X("start:Q", title="Time (seconds)"),
            x2="end:Q",
            color=alt.Color(
                "status:N",
                scale=alt.Scale(domain=status_domain, range=range_),
                legend=alt.Legend(title="Status"),
            ),
            tooltip=[
                alt.Tooltip("name:N", title="Phase"),
                alt.Tooltip("duration:Q", title="Duration (s)"),
                alt.Tooltip("tool_count:Q", title="Tool Calls"),
                alt.Tooltip("status:N", title="Status"),
            ],
        )
        .properties(
            width="container",
            height=max(len(rows) * 32, 120),
            title="Phase Timing Waterfall",
        )
    )
    return chart


def _refactoring_bar_chart(candidates: list[dict[str, Any]]) -> Any:
    """Horizontal bar chart of top-15 refactoring candidates by score."""
    import altair as alt

    if not candidates:
        return None

    top = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)[:15]

    rows = []
    for c in top:
        label = c.get("pattern", "unknown")
        if len(label) > 50:
            label = label[:47] + "..."
        rows.append(
            {
                "pattern": label,
                "score": round(c.get("score", 0), 2),
                "type": c.get("type", "unknown"),
                "occurrences": c.get("occurrence_count", 0),
            },
        )

    type_colors = {
        "extract_helper": "#a78bfa",
        "inline_wrapper": "#60a5fa",
        "dead_code": "#fbbf24",
        "code_smell": "#ef4444",
    }
    domain = sorted({r["type"] for r in rows})
    range_ = [type_colors.get(t, "#6a6a86") for t in domain]

    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y("pattern:N", sort="-x", title="Pattern"),
            x=alt.X("score:Q", title="Score"),
            color=alt.Color(
                "type:N",
                scale=alt.Scale(domain=domain, range=range_),
                legend=alt.Legend(title="Type"),
            ),
            tooltip=[
                alt.Tooltip("pattern:N", title="Pattern"),
                alt.Tooltip("score:Q", title="Score"),
                alt.Tooltip("type:N", title="Type"),
                alt.Tooltip("occurrences:Q", title="Occurrences"),
            ],
        )
        .properties(
            width="container",
            height=max(len(rows) * 28, 120),
            title="Refactoring Candidates (Top 15 by Score)",
        )
    )
    return chart


def _refactoring_cards(candidates: list[dict[str, Any]]) -> str:
    """Styled HTML cards for each refactoring candidate."""
    if not candidates:
        return _no_data("refactoring candidates")

    sorted_cands = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)

    type_badges: dict[str, str] = {
        "extract_helper": "#a78bfa",
        "inline_wrapper": "#60a5fa",
        "dead_code": "#fbbf24",
        "code_smell": "#ef4444",
    }

    cards = ""
    for c in sorted_cands:
        ctype = c.get("type", "unknown")
        badge_color = type_badges.get(ctype, "#6a6a86")
        pattern = (c.get("pattern") or "").replace("<", "&lt;").replace(">", "&gt;")
        occurrences = c.get("occurrence_count", 0)
        dup_lines = c.get("duplicated_lines", 0)
        score = c.get("score", 0)

        files_raw = c.get("files", [])
        files_html = ""
        if files_raw:
            file_items = "".join(
                f'<li style="font-family:monospace;font-size:0.78rem;color:#93c5fd">'
                f"{str(f).replace('<', '&lt;').replace('>', '&gt;')}</li>"
                for f in files_raw[:8]
            )
            extra = f'<li style="color:#888">... and {len(files_raw) - 8} more</li>' if len(files_raw) > 8 else ""
            files_html = f'<ul style="margin:4px 0 0 16px;padding:0;list-style:disc">{file_items}{extra}</ul>'

        stats = f"<span style='color:#aaa;font-size:0.8rem'>{occurrences} occurrences"
        if dup_lines > 0:
            stats += f" &middot; {dup_lines} duplicated lines"
        stats += f" &middot; score {score:.2f}</span>"

        cards += (
            f'<div style="background:#1e1e2e;border-radius:8px;padding:1rem 1.2rem;margin-bottom:0.6rem">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
            f'<span style="background:{badge_color};color:#fff;padding:1px 8px;border-radius:10px;'
            f'font-size:0.7rem;text-transform:uppercase">{ctype}</span>'
            f'<span style="color:#eee;font-weight:600;font-size:0.9rem">{pattern}</span>'
            f"</div>"
            f"{stats}"
            f"{files_html}"
            f"</div>"
        )

    return cards


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_insights_view(data: DashboardData) -> pn.viewable.Viewable:
    """Build the insights tab.

    Contains a phase timing waterfall chart and refactoring candidate
    charts/cards.
    """
    import panel as pn

    ar = data.analysis_result
    sections: list[Any] = []

    sections.append(pn.pane.Markdown("## Insights", sizing_mode="stretch_width"))

    if not ar:
        sections.append(
            pn.pane.Markdown(
                "*No analysis result available. Run an analysis first.*",
                sizing_mode="stretch_width",
            ),
        )
        return pn.Column(*sections, sizing_mode="stretch_width")

    # ---- 1. Phase timing waterfall ----
    timings = ar.get("phase_timings", [])
    if timings:
        chart = _phase_timing_chart(timings)
        if chart is not None:
            sections.append(pn.pane.Vega(chart, sizing_mode="stretch_width"))
    else:
        sections.append(pn.pane.Markdown(_no_data("phase timing")))

    # ---- 2. Refactoring candidates ----
    candidates = ar.get("refactoring_candidates", [])
    sections.append(
        pn.pane.HTML(
            '<h3 style="color:#eee;margin-top:1.5rem">Refactoring Candidates</h3>',
            sizing_mode="stretch_width",
        ),
    )
    if candidates:
        chart = _refactoring_bar_chart(candidates)
        if chart is not None:
            sections.append(pn.pane.Vega(chart, sizing_mode="stretch_width"))
        sections.append(pn.pane.HTML(_refactoring_cards(candidates), sizing_mode="stretch_width"))
    else:
        sections.append(pn.pane.Markdown(_no_data("refactoring candidates")))

    return pn.Column(*sections, sizing_mode="stretch_width")
