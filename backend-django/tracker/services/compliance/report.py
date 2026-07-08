"""
Auto-generated weekly compliance report (Freeman's template).

Groups the week's CaseEvent + ComplianceObservation rows by category_tag, computes
an activity-weighted breakdown per category against the target percentages, and
renders the report to text/HTML (always) and PDF (if weasyprint is installed).
Every figure traces to a row, so the report is also a timestamped record of work.

The assembly + render functions are pure (no DB); gather_week / build_report read
the DB. PDF needs `pip install weasyprint` (system cairo/pango); without it,
render_pdf returns None and text/HTML still work.
"""

from __future__ import annotations

import datetime as dt
import html
from dataclasses import dataclass, field

from django.utils import timezone

from tracker.models import CATEGORY_TAG_CHOICES, CATEGORY_TARGET_PCT
from tracker.services.property_intelligence import (
    PropertyIntelligenceReportSnapshot,
    intelligence_report_snapshot,
)

CATEGORY_LABELS = dict(CATEGORY_TAG_CHOICES)
CATEGORY_ORDER = [tag for tag, _ in CATEGORY_TAG_CHOICES]


@dataclass
class WeeklyReportData:
    start: dt.date
    end: dt.date
    prepared_by: str
    categories: dict = field(default_factory=dict)  # tag -> {count, actual_pct, target_pct, items}
    totals: dict = field(default_factory=dict)
    intelligence: PropertyIntelligenceReportSnapshot | None = None


def week_bounds(reference: dt.date | None = None) -> tuple[dt.date, dt.date]:
    """Monday..Sunday week containing `reference` (default today)."""
    reference = reference or dt.date.today()
    start = reference - dt.timedelta(days=reference.weekday())
    return start, start + dt.timedelta(days=6)


def _fmt_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def _parcel_of(obj) -> str:
    case = getattr(obj, "case", None)
    return getattr(case, "parcel_id", "") if case is not None else ""


def _event_item(event) -> dict:
    return {
        "date": _fmt_date(getattr(event, "occurred_at", None)),
        "parcel_id": _parcel_of(event),
        "label": getattr(event, "transition", "") or getattr(event, "note", "") or "event",
        "type": "event",
    }


def _obs_item(obs) -> dict:
    return {
        "date": _fmt_date(getattr(obs, "observed_at", None)),
        "parcel_id": _parcel_of(obs),
        "label": f"{getattr(obs, 'kind', '')} via {getattr(obs, 'source', '')}".strip(),
        "type": "observation",
    }


def assemble(
    start,
    end,
    prepared_by,
    events,
    observations,
    *,
    intelligence: PropertyIntelligenceReportSnapshot | None = None,
) -> WeeklyReportData:
    """Pure: bucket events + observations by category_tag into report data."""
    cats: dict = {tag: {"items": []} for tag in CATEGORY_ORDER}
    for event in events:
        cats.setdefault(event.category_tag, {"items": []})["items"].append(_event_item(event))
    for obs in observations:
        cats.setdefault(obs.category_tag, {"items": []})["items"].append(_obs_item(obs))

    total = sum(len(bucket["items"]) for bucket in cats.values())
    for tag, bucket in cats.items():
        bucket["count"] = len(bucket["items"])
        bucket["actual_pct"] = round(100.0 * bucket["count"] / total, 1) if total else 0.0
        bucket["target_pct"] = CATEGORY_TARGET_PCT.get(tag, 0)
        bucket["items"].sort(key=lambda item: item["date"])
    return WeeklyReportData(
        start=start,
        end=end,
        prepared_by=prepared_by,
        categories=cats,
        totals={"events": len(events), "observations": len(observations), "activities": total},
        intelligence=intelligence,
    )


def _summary(data: WeeklyReportData) -> str:
    total = data.totals.get("activities", 0)
    if not total:
        return "No compliance activity was logged this week."
    leaders = sorted(
        ((tag, b["count"]) for tag, b in data.categories.items() if b.get("count")),
        key=lambda kv: kv[1],
        reverse=True,
    )
    top = ", ".join(f"{CATEGORY_LABELS[tag]} ({count})" for tag, count in leaders[:3])
    return (
        f"{total} compliance activities were logged across "
        f"{data.totals.get('events', 0)} case events and "
        f"{data.totals.get('observations', 0)} observations, led by {top}."
    )


def render_text(data: WeeklyReportData) -> str:
    """Pure: plain-text rendering of Freeman's template."""
    lines = [
        "Weekly Compliance Report",
        f"Week of {data.start.isoformat()} to {data.end.isoformat()}",
        f"Prepared by {data.prepared_by}",
        "",
    ]
    if data.intelligence is not None:
        lines.extend(
            [
                data.intelligence.coverage_line,
                data.intelligence.discoveries_line,
                "",
            ]
        )
    for tag in CATEGORY_ORDER:
        bucket = data.categories.get(tag, {"count": 0, "actual_pct": 0.0, "target_pct": CATEGORY_TARGET_PCT.get(tag, 0), "items": []})
        lines.append(f"{CATEGORY_LABELS[tag]}  (target {bucket['target_pct']}%, actual {bucket['actual_pct']}%)")
        lines.append(f"  Activities logged: {bucket['count']}")
        for item in bucket["items"]:
            parcel = f"{item['parcel_id']}  " if item["parcel_id"] else ""
            lines.append(f"    {item['date']}  {parcel}{item['label']}")
        lines.append("")
    lines.append(f"Summary: {_summary(data)}")
    return "\n".join(lines)


def render_html(data: WeeklyReportData) -> str:
    """Pure: clean HTML rendering of Freeman's template."""
    esc = html.escape
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>Weekly Compliance Report</title>",
        "<style>body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#17231f;max-width:760px;margin:2rem auto;padding:0 1rem}"
        "h1{font-size:1.4rem;margin:0 0 .25rem}h2{font-size:1.05rem;border-bottom:1px solid #cbd8d3;padding-bottom:.2rem;margin-top:1.5rem}"
        ".meta{color:#4f625c}.target{color:#64746f;font-weight:400;font-size:.85em}ul{margin:.3rem 0 0;padding-left:1.2rem}"
        "li{margin:.1rem 0}.pid{color:#286457;font-variant-numeric:tabular-nums}.summary{margin-top:1.5rem;padding-top:.75rem;border-top:2px solid #cbd8d3}</style>",
        "</head><body>",
        "<h1>Weekly Compliance Report</h1>",
        f"<p class='meta'>Week of {data.start.isoformat()} to {data.end.isoformat()}<br>Prepared by {esc(data.prepared_by)}</p>",
    ]
    if data.intelligence is not None:
        parts.append("<h2>Property Intelligence</h2>")
        parts.append(f"<p>{esc(data.intelligence.coverage_line)}<br>{esc(data.intelligence.discoveries_line)}</p>")
    for tag in CATEGORY_ORDER:
        bucket = data.categories.get(tag, {"count": 0, "actual_pct": 0.0, "target_pct": CATEGORY_TARGET_PCT.get(tag, 0), "items": []})
        parts.append(
            f"<h2>{esc(CATEGORY_LABELS[tag])} "
            f"<span class='target'>(target {bucket['target_pct']}%, actual {bucket['actual_pct']}%)</span></h2>"
        )
        parts.append(f"<p>Activities logged: <strong>{bucket['count']}</strong></p>")
        if bucket["items"]:
            parts.append("<ul>")
            for item in bucket["items"]:
                pid = f"<span class='pid'>{esc(item['parcel_id'])}</span> " if item["parcel_id"] else ""
                parts.append(f"<li>{esc(item['date'])} - {pid}{esc(item['label'])}</li>")
            parts.append("</ul>")
    parts.append(f"<p class='summary'>{esc(_summary(data))}</p>")
    parts.append("</body></html>")
    return "".join(parts)


def render_pdf(html_str: str) -> bytes | None:
    """HTML -> PDF via weasyprint if available, else None (text/HTML always work)."""
    try:
        import weasyprint
    except Exception:  # pragma: no cover - optional dependency
        return None
    return weasyprint.HTML(string=html_str).write_pdf()


def gather_week(start: dt.date, end: dt.date, *, prepared_by: str = "Travis Gilbert") -> WeeklyReportData:
    """DB: collect the week's tagged CaseEvent + ComplianceObservation activity."""
    from tracker.models import CaseEvent, ComplianceObservation

    start_dt = timezone.make_aware(dt.datetime.combine(start, dt.time.min))
    end_dt = timezone.make_aware(dt.datetime.combine(end, dt.time.max))
    events = list(
        CaseEvent.objects.filter(occurred_at__range=(start_dt, end_dt)).select_related("case")
    )
    observations = list(
        ComplianceObservation.objects.filter(observed_at__range=(start_dt, end_dt)).select_related("case")
    )
    return assemble(
        start,
        end,
        prepared_by,
        events,
        observations,
        intelligence=intelligence_report_snapshot(start=start, end=end),
    )


def build_report(reference: dt.date | None = None, *, prepared_by: str = "Travis Gilbert") -> dict:
    """DB: build the full report for the week containing `reference`."""
    start, end = week_bounds(reference)
    data = gather_week(start, end, prepared_by=prepared_by)
    html_str = render_html(data)
    return {
        "data": data,
        "text": render_text(data),
        "html": html_str,
        "pdf": render_pdf(html_str),
    }
