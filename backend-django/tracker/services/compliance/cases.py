"""
Compliance case helpers and the manual activity logger.

Every status change and logged action becomes a CaseEvent with a category_tag, so
the weekly report reads from the same trail that is the defensible audit record.
Factual only: the schema has no field for motive or strategy.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from tracker.models import CaseEvent, ComplianceCase, ComplianceObservation

REHAB_WINDOW_DAYS = 365  # rehab_deadline = sale_date + 12 months


def ensure_case(property_obj, *, program: str = "", sale_date: dt.date | None = None) -> ComplianceCase:
    """Get-or-create the compliance case for a property, anchored by parcel id."""
    defaults = {
        "program": program or getattr(property_obj, "program", "") or "",
        "buyer": getattr(property_obj, "buyer", None),
        "sale_date": sale_date,
        "rehab_deadline": (sale_date + dt.timedelta(days=REHAB_WINDOW_DAYS)) if sale_date else None,
    }
    case, _ = ComplianceCase.objects.get_or_create(
        property=property_obj,
        parcel_id=getattr(property_obj, "parcel_id", "") or "",
        defaults=defaults,
    )
    return case


def record_case_event(
    case: ComplianceCase,
    *,
    transition: str,
    category_tag: str = "oversight_enforcement",
    actor: str = "staff",
    note: str = "",
    evidence_refs=None,
    occurred_at: dt.datetime | None = None,
) -> CaseEvent:
    """The manual activity logger: one CaseEvent per action, tagged for the report."""
    return CaseEvent.objects.create(
        case=case,
        transition=transition,
        category_tag=category_tag,
        actor=actor,
        note=note,
        evidence_refs=list(evidence_refs or []),
        occurred_at=occurred_at or timezone.now(),
    )


def transition_case(
    case: ComplianceCase,
    new_status: str,
    *,
    reason: str = "",
    actor: str = "staff",
    category_tag: str = "oversight_enforcement",
    evidence_refs=None,
) -> CaseEvent:
    """Move a case to a new lifecycle status and log the transition as a CaseEvent.

    Does NOT create or close ActionItem rows: ComplianceCase.status is a separate
    axis from the actionable queue.
    """
    old = case.status
    case.status = new_status
    case.save(update_fields=["status", "updated_at"])
    label = f"{old} -> {new_status}" + (f": {reason}" if reason else "")
    return record_case_event(
        case,
        transition=label,
        category_tag=category_tag,
        actor=actor,
        evidence_refs=evidence_refs,
    )


def log_observation(
    case: ComplianceCase,
    *,
    kind: str,
    source: str = "manual",
    category_tag: str = "data_governance",
    confidence: float | None = None,
    geo: dict | None = None,
    exif: dict | None = None,
    artifact_ref: str = "",
    document=None,
    created_by: str = "staff",
    observed_at: dt.datetime | None = None,
) -> ComplianceObservation:
    """Attach a tagged evidence observation to a case."""
    return ComplianceObservation.objects.create(
        case=case,
        kind=kind,
        source=source,
        category_tag=category_tag,
        confidence=confidence,
        geo=geo,
        exif=exif,
        artifact_ref=artifact_ref,
        document=document,
        created_by=created_by,
        observed_at=observed_at or timezone.now(),
    )
