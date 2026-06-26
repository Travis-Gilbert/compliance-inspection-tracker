from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable

from django.db import transaction
from django.utils import timezone

from tracker.models import (
    ActionItem,
    ComplianceCase,
    Property,
    TwentySyncRecord,
)
from tracker.services.workflow import build_action_queue


DEFAULT_TENANT_ID = "gclba"
DEFAULT_OBJECTS = (
    "property",
    "outreach",
    "compliance_case",
    "valuation_snapshot",
    "home_quality",
)

OBJECT_API_NAMES = {
    "property": "gclbaProperties",
    "outreach": "gclbaOutreachRecords",
    "compliance_case": "gclbaComplianceCases",
    "valuation_snapshot": "gclbaValuationSnapshots",
    "home_quality": "gclbaHomeQualityObservations",
}


@dataclass(frozen=True)
class TwentySyncCandidate:
    object_name: str
    object_api_name: str
    external_key: str
    payload: dict[str, Any]
    property_id: int | None = None
    action_item_id: int | None = None
    metadata: dict[str, Any] | None = None

    @property
    def payload_hash(self) -> str:
        encoded = json.dumps(
            self.payload,
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class TwentySyncResult:
    projected: int
    created: int
    updated: int
    unchanged: int
    candidates: int
    skipped: dict[str, int]


def build_twenty_sync_candidates(
    *,
    as_of: dt.date | None = None,
    objects: Iterable[str] = DEFAULT_OBJECTS,
    limit: int | None = 50,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> list[TwentySyncCandidate]:
    selected_objects = set(objects)
    properties = list(_property_queryset(limit=limit))
    candidates: list[TwentySyncCandidate] = []

    if "property" in selected_objects:
        candidates.extend(_property_candidates(properties, tenant_id=tenant_id))
    if "outreach" in selected_objects:
        candidates.extend(_outreach_candidates(properties, as_of=as_of))
    if "compliance_case" in selected_objects:
        candidates.extend(_compliance_case_candidates(properties))
    if "valuation_snapshot" in selected_objects:
        candidates.extend(_valuation_candidates(properties))
    if "home_quality" in selected_objects:
        candidates.extend(_home_quality_candidates(properties))

    return candidates


def sync_twenty_projection(
    *,
    as_of: dt.date | None = None,
    dry_run: bool = False,
    objects: Iterable[str] = DEFAULT_OBJECTS,
    limit: int | None = 50,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> TwentySyncResult:
    candidates = build_twenty_sync_candidates(
        as_of=as_of,
        objects=objects,
        limit=limit,
        tenant_id=tenant_id,
    )
    if dry_run:
        return TwentySyncResult(
            projected=0,
            created=0,
            updated=0,
            unchanged=0,
            candidates=len(candidates),
            skipped=_skipped_counts(objects),
        )

    created = 0
    updated = 0
    unchanged = 0
    now = timezone.now()

    with transaction.atomic():
        for candidate in candidates:
            existing = TwentySyncRecord.objects.filter(
                tenant_id=tenant_id,
                object_name=candidate.object_name,
                external_key=candidate.external_key,
            ).first()
            defaults = {
                "object_name": candidate.object_name,
                "payload_hash": candidate.payload_hash,
                "property_id": candidate.property_id,
                "action_item_id": candidate.action_item_id,
                "metadata": {
                    **(candidate.metadata or {}),
                    "objectApiName": candidate.object_api_name,
                    "payload": candidate.payload,
                    "projectedAt": now.isoformat(),
                },
                "last_error": "",
            }
            _, was_created = TwentySyncRecord.objects.update_or_create(
                tenant_id=tenant_id,
                object_name=candidate.object_name,
                external_key=candidate.external_key,
                defaults=defaults,
            )
            if was_created:
                created += 1
            elif existing and existing.payload_hash == candidate.payload_hash:
                unchanged += 1
            else:
                updated += 1

    return TwentySyncResult(
        projected=len(candidates),
        created=created,
        updated=updated,
        unchanged=unchanged,
        candidates=len(candidates),
        skipped=_skipped_counts(objects),
    )


def _property_queryset(*, limit: int | None) -> list[Property]:
    qs = (
        Property.objects.select_related("buyer", "program_record")
        .prefetch_related(
            "communications",
            "documents",
            "action_items",
            "compliance_cases",
            "photos",
        )
        .order_by("id")
    )
    if limit is None:
        return list(qs)
    return list(qs[: max(0, limit)])


def _property_candidates(
    properties: Iterable[Property],
    *,
    tenant_id: str,
) -> list[TwentySyncCandidate]:
    return [
        TwentySyncCandidate(
            object_name="property",
            object_api_name=OBJECT_API_NAMES["property"],
            external_key=f"property:{prop.id}",
            property_id=prop.id,
            payload={
                "djangoPropertyId": prop.id,
                "parcelId": prop.parcel_id,
                "tenantId": tenant_id,
                "address": prop.address,
                "buyerName": prop.buyer_name or None,
                "program": prop.program or None,
                "complianceStatus": _twenty_compliance_status(prop.compliance_status),
                "taxStatus": _twenty_tax_status(prop.tax_status),
                "crmUrl": _django_property_url(prop.id),
            },
            metadata=_base_metadata(prop),
        )
        for prop in properties
    ]


def _outreach_candidates(
    properties: list[Property],
    *,
    as_of: dt.date | None,
) -> list[TwentySyncCandidate]:
    queue = build_action_queue(properties, as_of=as_of)
    action_items = {
        (item.property_id, item.action): item
        for prop in properties
        for item in prop.action_items.all()
        if item.status in {"open", "in_progress"}
    }
    candidates: list[TwentySyncCandidate] = []

    for group in queue["groups"]:
        for item in group["items"]:
            prop_id = item["propertyId"]
            action = item["action"]
            action_item = action_items.get((prop_id, action))
            candidates.append(
                TwentySyncCandidate(
                    object_name="outreach",
                    object_api_name=OBJECT_API_NAMES["outreach"],
                    external_key=f"outreach:{prop_id}:{action}",
                    property_id=prop_id,
                    action_item_id=action_item.id if action_item else None,
                    payload={
                        "djangoPropertyId": prop_id,
                        "parcelId": item["parcelId"],
                        "action": _upper_or_default(action, "MANUAL_REVIEW"),
                        "method": "EMAIL" if item.get("email") else "MAIL",
                        "status": _twenty_outreach_status(item.get("status")),
                        "dueDate": item.get("dueDate"),
                    },
                    metadata={
                        "address": item["address"],
                        "buyerName": item["buyerName"],
                        "daysOverdue": item["daysOverdue"],
                        "priority": item["priority"],
                        "reasons": item["reasons"],
                        "source": item["source"],
                    },
                )
            )

    return candidates


def _compliance_case_candidates(properties: list[Property]) -> list[TwentySyncCandidate]:
    property_ids = [prop.id for prop in properties]
    cases = ComplianceCase.objects.filter(property_id__in=property_ids).select_related("property")

    return [
        TwentySyncCandidate(
            object_name="compliance_case",
            object_api_name=OBJECT_API_NAMES["compliance_case"],
            external_key=f"compliance_case:{case.id}",
            property_id=case.property_id,
            payload={
                "djangoPropertyId": case.property_id,
                "parcelId": case.parcel_id,
                "caseStatus": _twenty_case_status(case.status),
                "enforcementLevel": _case_enforcement_level(case.status),
                "nextReviewAt": case.rehab_deadline.isoformat() if case.rehab_deadline else None,
            },
            metadata={
                "caseId": case.id,
                "program": case.program,
                "sourceStatus": case.status,
            },
        )
        for case in cases
    ]


def _valuation_candidates(properties: Iterable[Property]) -> list[TwentySyncCandidate]:
    candidates = []
    for prop in properties:
        if prop.assessed_value is None and prop.taxable_value is None:
            continue
        candidates.append(
            TwentySyncCandidate(
                object_name="valuation_snapshot",
                object_api_name=OBJECT_API_NAMES["valuation_snapshot"],
                external_key=f"valuation_snapshot:{prop.id}:current",
                property_id=prop.id,
                payload={
                    "djangoPropertyId": prop.id,
                    "parcelId": prop.parcel_id,
                    "assessedValue": prop.assessed_value,
                    "taxableValue": prop.taxable_value,
                    "askingPrice": None,
                    "observedAt": prop.updated_at.isoformat() if prop.updated_at else None,
                },
                metadata=_base_metadata(prop),
            )
        )
    return candidates


def _home_quality_candidates(properties: Iterable[Property]) -> list[TwentySyncCandidate]:
    candidates = []
    for prop in properties:
        photo_summary = _photo_summary(prop)
        candidates.append(
            TwentySyncCandidate(
                object_name="home_quality",
                object_api_name=OBJECT_API_NAMES["home_quality"],
                external_key=f"home_quality:{prop.id}:current",
                property_id=prop.id,
                payload={
                    "djangoPropertyId": prop.id,
                    "parcelId": prop.parcel_id,
                    "qualityBand": _quality_band(prop),
                    "photoSummary": photo_summary,
                    "observedAt": prop.reviewed_at.isoformat()
                    if prop.reviewed_at
                    else prop.updated_at.isoformat(),
                },
                metadata={
                    **_base_metadata(prop),
                    "finding": prop.finding,
                    "detectionLabel": prop.detection_label,
                    "manualComplianceOutcome": prop.manual_compliance_outcome,
                },
            )
        )
    return candidates


def _base_metadata(prop: Property) -> dict[str, Any]:
    return {
        "address": prop.address,
        "parcelId": prop.parcel_id,
        "updatedAt": prop.updated_at.isoformat() if prop.updated_at else None,
    }


def _django_property_url(property_id: int) -> str:
    return f"/gclba/context?property={property_id}"


def _photo_summary(prop: Property) -> str | None:
    photos = list(prop.photos.all()) if hasattr(prop, "photos") else []
    if not photos:
        return None
    before_count = sum(photo.side == "before" for photo in photos)
    after_count = sum(photo.side == "after" for photo in photos)
    return f"{before_count} before / {after_count} after"


def _twenty_compliance_status(status: str | None) -> str:
    normalized = (status or "").lower()
    if normalized == "compliant":
        return "COMPLIANT"
    if normalized in {"needs_outreach", "in_progress"}:
        return "NEEDS_REVIEW"
    if normalized == "non_compliant":
        return "NON_COMPLIANT"
    return "UNKNOWN"


def _twenty_tax_status(status: str | None) -> str:
    normalized = (status or "").lower()
    if normalized == "current":
        return "CURRENT"
    if normalized == "delinquent":
        return "DELINQUENT"
    return "UNKNOWN"


def _twenty_outreach_status(status: str | None) -> str:
    normalized = (status or "logged").upper()
    if normalized in {"LOGGED", "DRAFT", "SENT", "DELIVERED", "BOUNCED", "FAILED"}:
        return normalized
    return "LOGGED"


def _twenty_case_status(status: str | None) -> str:
    normalized = (status or "").lower()
    if normalized in {"closed"}:
        return "RESOLVED"
    if normalized in {"escalated", "non_compliant"}:
        return "ENFORCEMENT"
    if normalized == "at_risk":
        return "WARNING"
    if normalized == "on_track":
        return "INSPECTION"
    return "OPEN"


def _case_enforcement_level(status: str | None) -> int:
    normalized = (status or "").lower()
    if normalized == "escalated":
        return 4
    if normalized == "non_compliant":
        return 3
    if normalized == "at_risk":
        return 2
    return 0


def _quality_band(prop: Property) -> str:
    outcome = prop.manual_compliance_outcome
    if outcome == "compliant":
        return "GOOD"
    if outcome == "in_progress":
        return "FAIR"
    if outcome == "non_compliant":
        return "POOR"
    if prop.detection_label in {"vacant", "demolished", "structure_gone"}:
        return "POOR"
    return "UNKNOWN"


def _upper_or_default(value: str | None, default: str) -> str:
    return value.upper() if value else default


def _skipped_counts(objects: Iterable[str]) -> dict[str, int]:
    selected = set(objects)
    skipped: dict[str, int] = {}
    if "opportunity_zone" not in selected:
        return skipped
    skipped["opportunity_zone"] = 0
    return skipped
