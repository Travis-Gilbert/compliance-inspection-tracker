"""
Per-parcel visual timeline assembly (P4).

Timeline position is derived, never stored: order by capture date within a
source, anchor against closing date, and tag BEFORE / CURRENT for comparison UI.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Optional

from tracker.models import Property, PropertyImageEvidence


@dataclass(frozen=True)
class TimelineEntry:
    evidence_id: int
    image_source: str
    capture_date: str
    capture_date_precision: str
    image_url: str
    pano_id: str
    storage_key: str
    tag: str  # BEFORE | CURRENT | OTHER
    superseded: bool


@dataclass(frozen=True)
class PropertyTimeline:
    property_id: int
    parcel_id: str
    closing_date: str
    entries: list[TimelineEntry]
    before: TimelineEntry | None
    current: TimelineEntry | None


def _parse_sort_key(capture_date: str) -> str:
    """Pad partial dates so lexicographic order roughly matches chronology."""
    text = (capture_date or "").strip()
    if not text:
        return ""
    if len(text) == 4:
        return f"{text}-01-01"
    if len(text) == 7:
        return f"{text}-01"
    return text


def _parse_closing(closing_date: str) -> str:
    text = (closing_date or "").strip()
    if not text:
        return ""
    # Accept YYYY-MM-DD or loose strings starting with a date.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y-%m"):
        try:
            parsed = dt.datetime.strptime(text[:10] if fmt != "%Y-%m" else text[:7], fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    return ""


def active_evidence_qs(property_id: int | None = None):
    qs = PropertyImageEvidence.objects.filter(superseded_by__isnull=True)
    if property_id is not None:
        qs = qs.filter(property_id=property_id)
    return qs


def assemble_timeline(
    prop: Property,
    *,
    sources: Iterable[str] | None = None,
    include_superseded: bool = False,
) -> PropertyTimeline:
    qs = PropertyImageEvidence.objects.filter(property=prop)
    if not include_superseded:
        qs = qs.filter(superseded_by__isnull=True)
    if sources:
        qs = qs.filter(image_source__in=list(sources))

    rows = list(qs)
    rows.sort(key=lambda r: (_parse_sort_key(r.capture_date), r.id))

    closing = _parse_closing(prop.closing_date)
    before: TimelineEntry | None = None
    current: TimelineEntry | None = None
    entries: list[TimelineEntry] = []

    dated = [r for r in rows if r.capture_date]
    if closing and dated:
        before_candidates = [
            r for r in dated if _parse_sort_key(r.capture_date) < closing
        ]
        after_or_on = [
            r for r in dated if _parse_sort_key(r.capture_date) >= closing
        ]
        if before_candidates:
            before_row = before_candidates[-1]
        else:
            before_row = None
        current_row = after_or_on[-1] if after_or_on else (dated[-1] if dated else None)
    elif dated:
        before_row = None
        current_row = dated[-1]
    else:
        before_row = None
        current_row = None

    for row in rows:
        tag = "OTHER"
        if before_row is not None and row.id == before_row.id:
            tag = "BEFORE"
        elif current_row is not None and row.id == current_row.id:
            tag = "CURRENT"
        entry = TimelineEntry(
            evidence_id=row.id,
            image_source=row.image_source,
            capture_date=row.capture_date,
            capture_date_precision=row.capture_date_precision,
            image_url=row.image_url,
            pano_id=row.pano_id,
            storage_key=row.storage_key,
            tag=tag,
            superseded=row.superseded_by_id is not None,
        )
        entries.append(entry)
        if tag == "BEFORE":
            before = entry
        elif tag == "CURRENT":
            current = entry

    return PropertyTimeline(
        property_id=prop.id,
        parcel_id=prop.parcel_id,
        closing_date=closing,
        entries=entries,
        before=before,
        current=current,
    )
