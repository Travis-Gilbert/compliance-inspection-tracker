from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urlencode

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from tracker.models import (
    ActionItem,
    ComplianceCase,
    Property,
    SourceConflict,
    TwentySyncRecord,
)
from tracker.services.enrichment import parse_closing_date
from tracker.services.workflow import build_action_queue


DEFAULT_TENANT_ID = "gclba"
DEFAULT_OBJECTS = (
    "property",
    "outreach",
    "compliance_case",
    "source_conflict",
    "valuation_snapshot",
    "home_quality",
    "image_evidence",
)
TWENTY_CLOUD_BASE_URL = "https://api.twenty.com"

OBJECT_API_NAMES = {
    "property": "gclbaProperties",
    "outreach": "gclbaOutreachRecords",
    "compliance_case": "gclbaComplianceCases",
    "source_conflict": "gclbaSourceConflicts",
    "valuation_snapshot": "gclbaValuationSnapshots",
    "home_quality": "gclbaHomeQualityObservations",
    "image_evidence": "gclbaImageEvidenceItems",
}

# Twenty frontend deep links use nameSingular; REST uses namePlural.
OBJECT_UI_NAMES = {
    "gclbaProperties": "gclbaProperty",
    "gclbaOutreachRecords": "gclbaOutreachRecord",
    "gclbaComplianceCases": "gclbaComplianceCase",
    "gclbaSourceConflicts": "gclbaSourceConflict",
    "gclbaValuationSnapshots": "gclbaValuationSnapshot",
    "gclbaHomeQualityObservations": "gclbaHomeQualityObservation",
    "gclbaImageEvidenceItems": "gclbaImageEvidence",
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
    delivered: int = 0
    failed: int = 0


@dataclass(frozen=True)
class TwentyDeliveryResult:
    record_id: str
    record_url: str = ""


class TwentyDeliveryError(RuntimeError):
    pass


class TwentyClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        frontend_url: str = "",
        rate_limit_per_minute: int = 90,
        client: httpx.Client | None = None,
    ):
        if not base_url:
            raise ValueError("TWENTY_BASE_URL is required for --push")
        if not api_key:
            raise ValueError("TWENTY_API_KEY is required for --push")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.frontend_url = (frontend_url or base_url).rstrip("/")
        self.rate_limit_per_minute = max(1, rate_limit_per_minute)
        self._window_started_at = time.monotonic()
        self._window_request_count = 0
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=30.0)

    @classmethod
    def from_settings(cls) -> "TwentyClient":
        return cls(
            base_url=settings.TWENTY_BASE_URL or TWENTY_CLOUD_BASE_URL,
            api_key=settings.TWENTY_API_KEY,
            frontend_url=getattr(settings, "TWENTY_FRONTEND_URL", ""),
            rate_limit_per_minute=getattr(settings, "TWENTY_RATE_LIMIT_PER_MINUTE", 90),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def upsert_record(
        self,
        candidate: TwentySyncCandidate,
        *,
        existing_record_id: str = "",
    ) -> TwentyDeliveryResult:
        if existing_record_id:
            response = self._request(
                "PATCH",
                f"/rest/{candidate.object_api_name}/{existing_record_id}",
                candidate.payload,
                allow_not_found=True,
            )
            if response is not None:
                record_id = _extract_record_id(response) or existing_record_id
                return TwentyDeliveryResult(
                    record_id=record_id,
                    record_url=_record_url(self.frontend_url, candidate.object_api_name, record_id),
                )

        created = self._request(
            "POST",
            f"/rest/{candidate.object_api_name}",
            candidate.payload,
            allow_not_found=False,
        )
        record_id = _extract_record_id(created)
        if not record_id:
            raise TwentyDeliveryError(
                f"Twenty response for {candidate.object_api_name} did not include a record id"
            )
        return TwentyDeliveryResult(
            record_id=record_id,
            record_url=_record_url(self.frontend_url, candidate.object_api_name, record_id),
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        *,
        allow_not_found: bool,
    ) -> dict[str, Any] | None:
        response = None
        for attempt in range(3):
            self._throttle()
            response = self._client.request(
                method,
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code != 429:
                break
            retry_after = _retry_after_seconds(response)
            if attempt < 2:
                time.sleep(retry_after)
        assert response is not None
        if allow_not_found and response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise TwentyDeliveryError(
                f"Twenty {method} {path} failed with {response.status_code}: "
                f"{response.text[:500]}"
            )
        try:
            decoded = response.json()
        except ValueError as exc:
            raise TwentyDeliveryError(
                f"Twenty {method} {path} returned non-JSON response"
            ) from exc
        if not isinstance(decoded, dict):
            raise TwentyDeliveryError(
                f"Twenty {method} {path} returned an unexpected response shape"
            )
        return decoded

    def _throttle(self) -> None:
        now = time.monotonic()
        elapsed = now - self._window_started_at
        if elapsed >= 60:
            self._window_started_at = now
            self._window_request_count = 0
            return
        if self._window_request_count >= self.rate_limit_per_minute:
            time.sleep(60 - elapsed)
            self._window_started_at = time.monotonic()
            self._window_request_count = 0
        self._window_request_count += 1


def _extract_record_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("id", "recordId"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        for key in ("data", "record"):
            value = _extract_record_id(payload.get(key))
            if value:
                return value
        for value in payload.values():
            nested = _extract_record_id(value)
            if nested:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = _extract_record_id(item)
            if nested:
                return nested
    return ""


def _retry_after_seconds(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After")
    if not raw:
        return 60.0
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


def _record_url(frontend_url: str, object_api_name: str, record_id: str) -> str:
    if not frontend_url or not record_id:
        return ""
    ui_name = OBJECT_UI_NAMES.get(object_api_name, object_api_name)
    return f"{frontend_url.rstrip('/')}/object/{ui_name}/{record_id}"


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
    if "source_conflict" in selected_objects:
        candidates.extend(_source_conflict_candidates(properties))
    if "valuation_snapshot" in selected_objects:
        candidates.extend(_valuation_candidates(properties))
    if "home_quality" in selected_objects:
        candidates.extend(_home_quality_candidates(properties))
    if "image_evidence" in selected_objects:
        candidates.extend(_image_evidence_candidates(properties))

    return candidates


def sync_twenty_projection(
    *,
    as_of: dt.date | None = None,
    dry_run: bool = False,
    objects: Iterable[str] = DEFAULT_OBJECTS,
    limit: int | None = 50,
    tenant_id: str = DEFAULT_TENANT_ID,
    push: bool = False,
    force: bool = False,
    client: TwentyClient | None = None,
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
    delivered = 0
    failed = 0
    now = timezone.now()
    active_client = client
    owns_client = False
    if push and active_client is None:
        active_client = TwentyClient.from_settings()
        owns_client = True

    try:
        for candidate in candidates:
            with transaction.atomic():
                existing = TwentySyncRecord.objects.filter(
                    tenant_id=tenant_id,
                    object_name=candidate.object_name,
                    external_key=candidate.external_key,
                ).first()
                previous_hash = existing.payload_hash if existing else ""
                previous_twenty_id = existing.twenty_record_id if existing else ""
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
                record, was_created = TwentySyncRecord.objects.update_or_create(
                    tenant_id=tenant_id,
                    object_name=candidate.object_name,
                    external_key=candidate.external_key,
                    defaults=defaults,
                )
                if was_created:
                    created += 1
                elif previous_hash == candidate.payload_hash:
                    unchanged += 1
                else:
                    updated += 1

            should_deliver = push and (
                force
                or bool(record.last_error)
                or was_created
                or previous_hash != candidate.payload_hash
                or not previous_twenty_id
            )
            if should_deliver and active_client:
                try:
                    delivery = active_client.upsert_record(
                        candidate,
                        existing_record_id=previous_twenty_id,
                    )
                except Exception as exc:
                    failed += 1
                    record.last_error = str(exc)
                    record.save(update_fields=["last_error", "updated_at"])
                else:
                    delivered += 1
                    record.twenty_record_id = delivery.record_id
                    record.twenty_url = delivery.record_url
                    record.last_synced_at = timezone.now()
                    record.last_error = ""
                    record.save(
                        update_fields=[
                            "twenty_record_id",
                            "twenty_url",
                            "last_synced_at",
                            "last_error",
                            "updated_at",
                        ]
                    )
    finally:
        if owns_client and active_client:
            active_client.close()

    return TwentySyncResult(
        projected=len(candidates),
        created=created,
        updated=updated,
        unchanged=unchanged,
        candidates=len(candidates),
        skipped=_skipped_counts(objects),
        delivered=delivered,
        failed=failed,
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
            "image_evidence__superseded_by",
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
                "name": _property_label(prop),
                "djangoPropertyId": prop.id,
                "parcelId": prop.parcel_id,
                "tenantId": tenant_id,
                "propertyAddress": _twenty_property_address(prop),
                "buyerName": _buyer_name(prop),
                "contactEmail": _contact_email(prop),
                "contactPhone": _contact_phone(prop),
                "organization": _organization(prop),
                "program": prop.program or None,
                "saleDate": _date_text(parse_closing_date(prop.closing_date or "")),
                "purchaseType": prop.purchase_type or None,
                "commitment": prop.commitment or None,
                "complianceStatus": _twenty_compliance_status(prop.compliance_status),
                "taxStatus": _twenty_tax_status(prop.tax_status),
                "taxAmountOwed": _number(prop.tax_amount_owed),
                "lastTaxPayment": _date_text(prop.last_tax_payment),
                "homeownerExemption": prop.homeowner_exemption,
                "assessedValue": _number(prop.assessed_value),
                "taxableValue": _number(prop.taxable_value),
                "ownerOfRecord": prop.owner_of_record or None,
                "propertyClass": prop.property_class or None,
                "landUse": prop.land_use or None,
                "forfeitureStatus": prop.forfeiture_status or None,
                "forfeitureStatusYear": prop.forfeiture_status_year or None,
                "finding": prop.finding or None,
                "detectionLabel": prop.detection_label or None,
                "regridCondition": prop.regrid_condition or None,
                "portalSurveyDate": _date_text(prop.portal_survey_date),
                "lastOutreachDate": _date_text(prop.last_outreach_date),
                "lastOutreachMethod": prop.last_outreach_method or None,
                "outreachAttempts": prop.outreach_attempts,
                "latitude": _number(prop.latitude),
                "longitude": _number(prop.longitude),
                "reviewedAt": _date_time_text(prop.reviewed_at),
                "reviewNotes": prop.notes or None,
                "crmUrl": _django_property_url(prop.id),
            },
            metadata=_base_metadata(prop),
        )
        for prop in properties
    ]


def _twenty_property_address(prop: Property) -> str:
    if prop.address and prop.address.strip():
        return prop.address
    if prop.parcel_id and prop.parcel_id.strip():
        return f"Address unavailable for parcel {prop.parcel_id}"
    return f"Address unavailable for property {prop.id}"


def _buyer_name(prop: Property) -> str | None:
    buyer = getattr(prop, "buyer", None)
    return (
        prop.buyer_name
        or (buyer.full_name if buyer else "")
        or _organization(prop)
        or None
    )


def _contact_email(prop: Property) -> str | None:
    buyer = getattr(prop, "buyer", None)
    return prop.email or (buyer.email if buyer else "") or None


def _contact_phone(prop: Property) -> str | None:
    buyer = getattr(prop, "buyer", None)
    return (buyer.phone if buyer else "") or None


def _organization(prop: Property) -> str | None:
    buyer = getattr(prop, "buyer", None)
    return prop.organization or (buyer.organization if buyer else "") or None


def _property_label(prop: Property) -> str:
    return (
        _buyer_name(prop)
        or _contact_email(prop)
        or prop.address
        or prop.parcel_id
        or f"Property {prop.id}"
    )


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
                        "name": f"{item['parcelId']} {action.replace('_', ' ').title()}",
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
                "name": f"{case.parcel_id} compliance case",
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


def _source_conflict_candidates(properties: list[Property]) -> list[TwentySyncCandidate]:
    property_ids = [prop.id for prop in properties]
    conflicts = SourceConflict.objects.filter(
        property_id__in=property_ids,
        status="open",
    ).select_related("property")

    return [
        TwentySyncCandidate(
            object_name="source_conflict",
            object_api_name=OBJECT_API_NAMES["source_conflict"],
            external_key=f"source_conflict:{conflict.id}",
            property_id=conflict.property_id,
            payload={
                "name": conflict.title or f"{conflict.parcel_id} source conflict",
                "djangoConflictId": conflict.id,
                "djangoPropertyId": conflict.property_id,
                "parcelId": conflict.parcel_id,
                "kind": _upper_or_default(conflict.kind, "OWNER_MISMATCH"),
                "severity": _upper_or_default(conflict.severity, "REVIEW"),
                "title": conflict.title,
                "plainLanguage": conflict.plain_language or None,
                "observedAt": conflict.observed_at.isoformat(),
                "status": _upper_or_default(conflict.status, "OPEN"),
                "crmUrl": _django_property_url(conflict.property_id)
                if conflict.property_id
                else "",
            },
            metadata={
                "conflictId": conflict.id,
                "evidence": conflict.evidence,
                "source": conflict.source,
                "externalKey": conflict.external_key,
            },
        )
        for conflict in conflicts
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
                    "name": f"{prop.parcel_id} valuation",
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
                    "name": _home_quality_label(prop),
                    "djangoPropertyId": prop.id,
                    "parcelId": prop.parcel_id,
                    "propertyAddress": prop.address,
                    "qualityBand": _quality_band(prop),
                    "photoSummary": photo_summary,
                    "streetviewAvailable": bool(prop.streetview_available),
                    "streetviewDate": prop.streetview_date or None,
                    "historicalStreetviewDate": prop.streetview_historical_date or None,
                    "satelliteAvailable": bool(prop.satellite_path),
                    "imageryFetchedAt": _date_time_text(prop.imagery_fetched_at),
                    "detectionLabel": prop.detection_label or None,
                    "detectionScore": _number(prop.detection_score),
                    "detectionDetails": _detection_details_summary(prop),
                    "reviewFinding": prop.finding or None,
                    "manualComplianceOutcome": prop.manual_compliance_outcome,
                    "reviewedAt": _date_time_text(prop.reviewed_at),
                    "regridCondition": prop.regrid_condition or None,
                    "portalSurveyDate": _date_text(prop.portal_survey_date),
                    "mapDossierUrl": _django_property_url(prop.id),
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


def _image_evidence_candidates(properties: Iterable[Property]) -> list[TwentySyncCandidate]:
    candidates: list[TwentySyncCandidate] = []
    for prop in properties:
        evidence_rows = list(prop.image_evidence.all()) if hasattr(prop, "image_evidence") else []
        evidence_sources = {row.image_source for row in evidence_rows}
        has_naip = "NAIP_AERIAL" in evidence_sources

        # Canonical multi-vintage / pointer rows from photo intake.
        for row in evidence_rows:
            image_url = _public_image_url(row.image_url) if row.image_url else ""
            if not image_url and row.storage_key:
                image_url = _public_image_url(row.storage_key)
            # Licensed pointers may only have a proxy path; still project them.
            if not image_url and row.pano_id:
                image_url = row.image_url or f"/api/imagery/pano/{row.pano_id}"
            if not image_url and not row.pano_id:
                continue
            external_key = _intake_evidence_external_key(prop.id, row)
            superseded_key = ""
            if row.superseded_by_id and row.superseded_by:
                superseded_key = _resolve_superseded_by_twenty_id(
                    prop.id, row.superseded_by
                )
            candidates.append(
                _image_evidence_candidate(
                    prop,
                    external_key=external_key,
                    name=f"{_image_property_label(prop)} {row.image_kind.lower().replace('_', ' ')}",
                    image_source=row.image_source,
                    image_kind=row.image_kind,
                    image_url=image_url,
                    thumbnail_url=_public_image_url(row.thumbnail_url) or image_url,
                    capture_date=row.capture_date,
                    attribution=row.attribution,
                    provider_record_id=row.provider_record_id or row.pano_id or row.sha256,
                    observed_at=row.updated_at or row.ingested_at or prop.updated_at,
                    capture_date_precision=row.capture_date_precision or None,
                    storage_key=row.storage_key or None,
                    sha256=row.sha256 or None,
                    pano_id=row.pano_id or None,
                    source_license=row.source_license or None,
                    superseded_by=superseded_key or None,
                    footprint_meters=_number(row.footprint_meters),
                    heading_degrees=_number(row.heading_degrees),
                    django_evidence_id=row.id,
                )
            )

        # Legacy Property.* imagery fields — skip when intake already covers the source.
        image_rows = (
            {
                "source": "STREET_VIEW",
                "kind": "EXTERIOR",
                "path": prop.streetview_path,
                "capture_date": prop.streetview_date,
                "attribution": "Google Street View",
                "provider_record_id": prop.streetview_date or "",
                "external_suffix": "streetview",
                "skip": "STREET_VIEW" in evidence_sources,
            },
            {
                "source": "HISTORICAL_STREET_VIEW",
                "kind": "HISTORICAL_EXTERIOR",
                "path": prop.streetview_historical_path,
                "capture_date": prop.streetview_historical_date,
                "attribution": "Google Street View",
                "provider_record_id": prop.streetview_historical_date or "",
                "external_suffix": "streetview_historical",
                # Keep legacy historical until intake has at least one pointer row.
                "skip": "HISTORICAL_STREET_VIEW" in evidence_sources,
            },
            {
                "source": "SATELLITE",
                "kind": "AERIAL",
                "path": prop.satellite_path,
                "capture_date": "",
                "attribution": "Google Static Maps satellite",
                "provider_record_id": "",
                "external_suffix": "satellite",
                # Prefer NAIP / materialized satellite evidence over undated legacy.
                "skip": "SATELLITE" in evidence_sources or has_naip,
            },
        )
        for row in image_rows:
            if row["skip"]:
                continue
            image_url = _public_image_url(row["path"])
            if not image_url:
                continue
            candidates.append(
                _image_evidence_candidate(
                    prop,
                    external_key=f"image_evidence:{prop.id}:{row['external_suffix']}",
                    name=f"{_image_property_label(prop)} {row['kind'].lower().replace('_', ' ')}",
                    image_source=row["source"],
                    image_kind=row["kind"],
                    image_url=image_url,
                    thumbnail_url=image_url,
                    capture_date=row["capture_date"],
                    attribution=row["attribution"],
                    provider_record_id=row["provider_record_id"],
                    observed_at=prop.imagery_fetched_at or prop.updated_at,
                    source_license="LICENSED_DISPLAY_ONLY",
                )
            )

        photos = list(prop.photos.all()) if hasattr(prop, "photos") else []
        for photo in photos:
            image_url = _photo_public_image_url(photo)
            if not image_url:
                continue
            image_kind = _photo_image_kind(photo.side)
            candidates.append(
                _image_evidence_candidate(
                    prop,
                    external_key=f"image_evidence:{prop.id}:photo:{photo.id}",
                    name=f"{_image_property_label(prop)} {image_kind.lower()} photo",
                    image_source="STAFF_UPLOAD",
                    image_kind=image_kind,
                    image_url=image_url,
                    thumbnail_url=image_url,
                    capture_date=_date_text(photo.photo_date) or "",
                    attribution=photo.source or "GCLBA staff upload",
                    provider_record_id=photo.original_filename or f"property-photo-{photo.id}",
                    observed_at=photo.uploaded_at or photo.updated_at or prop.updated_at,
                    django_photo_id=photo.id,
                    proximity_status=_twenty_proximity_status(photo.proximity_status),
                    match_distance_meters=_number(photo.distance_from_property_meters),
                    is_primary=photo.is_primary,
                    source_license="ORG_OWNED",
                )
            )
    return candidates


def _intake_evidence_external_key(property_id: int, row: Any) -> str:
    """Stable identity key: source + capture date (owned) or pano id (licensed)."""
    source = row.image_source
    if source in {"STREET_VIEW", "HISTORICAL_STREET_VIEW"} and row.pano_id:
        return f"image_evidence:{property_id}:{source}:{row.pano_id}"
    if row.capture_date:
        return f"image_evidence:{property_id}:{source}:{row.capture_date}"
    if row.sha256:
        return f"image_evidence:{property_id}:{source}:sha:{row.sha256[:16]}"
    return f"image_evidence:{property_id}:evidence:{row.id}"


def _resolve_superseded_by_twenty_id(property_id: int, target: Any) -> str:
    external_key = _intake_evidence_external_key(property_id, target)
    record = (
        TwentySyncRecord.objects.filter(
            object_name="image_evidence",
            external_key=external_key,
        )
        .exclude(twenty_record_id="")
        .order_by("-updated_at")
        .first()
    )
    if record and record.twenty_record_id:
        return record.twenty_record_id
    return external_key


def _image_evidence_candidate(
    prop: Property,
    *,
    external_key: str,
    name: str,
    image_source: str,
    image_kind: str,
    image_url: str,
    thumbnail_url: str,
    capture_date: str,
    attribution: str,
    provider_record_id: str,
    observed_at: dt.datetime | None,
    django_photo_id: int | None = None,
    django_evidence_id: int | None = None,
    proximity_status: str = "NOT_APPLICABLE",
    match_distance_meters: float | int | None = None,
    is_primary: bool = False,
    capture_date_precision: str | None = None,
    storage_key: str | None = None,
    sha256: str | None = None,
    pano_id: str | None = None,
    source_license: str | None = None,
    superseded_by: str | None = None,
    footprint_meters: float | int | None = None,
    heading_degrees: float | int | None = None,
) -> TwentySyncCandidate:
    return TwentySyncCandidate(
        object_name="image_evidence",
        object_api_name=OBJECT_API_NAMES["image_evidence"],
        external_key=external_key,
        property_id=prop.id,
        payload={
            "name": name,
            "djangoPropertyId": prop.id,
            "djangoPhotoId": django_photo_id,
            "djangoEvidenceId": django_evidence_id,
            "parcelId": prop.parcel_id,
            "propertyAddress": prop.address or None,
            "imageSource": image_source,
            "imageKind": image_kind,
            "imageUrl": image_url,
            "thumbnailUrl": thumbnail_url or None,
            "captureDate": capture_date or None,
            "captureDatePrecision": capture_date_precision,
            "storageKey": storage_key,
            "sha256": sha256,
            "panoId": pano_id,
            "sourceLicense": source_license,
            "supersededBy": superseded_by,
            "footprintMeters": footprint_meters,
            "headingDegrees": heading_degrees,
            "attribution": attribution or None,
            "providerRecordId": provider_record_id or None,
            "qualityBand": _quality_band(prop),
            "detectionLabel": prop.detection_label or None,
            "detectionScore": _number(prop.detection_score),
            "proximityStatus": proximity_status,
            "matchDistanceMeters": match_distance_meters,
            "isPrimary": is_primary,
            "mapDossierUrl": _django_property_url(prop.id),
            "observedAt": _date_time_text(observed_at) or _date_time_text(prop.updated_at),
        },
        metadata={
            **_base_metadata(prop),
            "imageSource": image_source,
            "imageKind": image_kind,
            "imageUrl": image_url,
            "djangoPhotoId": django_photo_id,
            "djangoEvidenceId": django_evidence_id,
            "supersededBy": superseded_by,
        },
    )


def _base_metadata(prop: Property) -> dict[str, Any]:
    return {
        "address": prop.address,
        "parcelId": prop.parcel_id,
        "updatedAt": prop.updated_at.isoformat() if prop.updated_at else None,
    }


def _home_quality_label(prop: Property) -> str:
    address = (prop.address or "").strip()
    if address:
        return f"{address} home quality"
    if prop.parcel_id:
        return f"{prop.parcel_id} home quality"
    return f"Property {prop.id} home quality"


def _image_property_label(prop: Property) -> str:
    address = (prop.address or "").strip()
    if address:
        return address
    if prop.parcel_id:
        return prop.parcel_id
    return f"Property {prop.id}"


def _django_property_url(property_id: int) -> str:
    base_url = getattr(settings, "GCLBA_MAP_URL", "").strip().rstrip("/") or "/gclba/context"
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'property': property_id})}"


def _public_image_url(raw_path: str | None) -> str:
    raw = (raw_path or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw

    media_url = getattr(settings, "MEDIA_URL", "/images/") or "/images/"
    media_prefix = media_url.rstrip("/") + "/"
    if raw.startswith(media_prefix):
        relative_url = raw
    else:
        relative_path = _relative_media_path(raw)
        if not relative_path:
            return ""
        relative_url = f"{media_prefix}{quote(relative_path, safe='/')}"

    public_base = getattr(settings, "GCLBA_BACKEND_PUBLIC_URL", "").strip().rstrip("/")
    if public_base and relative_url.startswith("/"):
        return f"{public_base}{relative_url}"
    return relative_url


def _photo_public_image_url(photo: Any) -> str:
    try:
        image_url = photo.public_url
    except Exception:
        image_url = ""
    if image_url:
        return _public_image_url(image_url)
    image = getattr(photo, "image", None)
    image_name = getattr(image, "name", "") if image else ""
    return _public_image_url(image_name)


def _relative_media_path(raw_path: str) -> str:
    raw = raw_path.strip()
    if not raw:
        return ""

    path = Path(raw)
    if path.is_absolute():
        for root in (getattr(settings, "MEDIA_ROOT", ""), getattr(settings, "IMAGE_CACHE_DIR", "")):
            if not root:
                continue
            try:
                return path.relative_to(Path(root)).as_posix()
            except ValueError:
                continue
        return path.name

    media_url = getattr(settings, "MEDIA_URL", "/images/") or "/images/"
    media_prefix = media_url.strip("/")
    if media_prefix and raw.startswith(f"{media_prefix}/"):
        return raw[len(media_prefix) + 1 :]
    return raw.lstrip("/")


def _photo_summary(prop: Property) -> str | None:
    photos = list(prop.photos.all()) if hasattr(prop, "photos") else []
    before_count = sum(photo.side == "before" for photo in photos)
    after_count = sum(photo.side == "after" for photo in photos)
    parts = [f"{before_count} before / {after_count} after uploads"]
    if prop.streetview_available:
        date = f" ({prop.streetview_date})" if prop.streetview_date else ""
        parts.append(f"Street View available{date}")
    if prop.streetview_historical_path:
        date = (
            f" ({prop.streetview_historical_date})"
            if prop.streetview_historical_date
            else ""
        )
        parts.append(f"historical Street View available{date}")
    if prop.satellite_path:
        parts.append("satellite image available")
    if len(parts) == 1 and before_count == 0 and after_count == 0:
        return None
    return "; ".join(parts)


def _detection_details_summary(prop: Property) -> str | None:
    details = prop.detection_details or {}
    if not details:
        return None
    signals = details.get("signals") if isinstance(details.get("signals"), dict) else {}
    if not signals:
        reason = details.get("reason")
        return str(reason) if reason else None
    return ", ".join(
        f"{key}: {value}"
        for key, value in sorted(signals.items())
        if isinstance(value, (int, float, str))
    )[:1000]


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
    if normalized == "payment_plan":
        return "PAYMENT_PLAN"
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
    if prop.detection_label in {
        "vacant",
        "demolished",
        "structure_gone",
        "likely_vacant",
        "likely_demolished",
    }:
        return "POOR"
    return "UNKNOWN"


def _photo_image_kind(side: str | None) -> str:
    normalized = (side or "").lower()
    if normalized == "before":
        return "BEFORE"
    if normalized == "after":
        return "AFTER"
    return "OTHER"


def _twenty_proximity_status(status: str | None) -> str:
    normalized = (status or "unlocated").upper()
    if normalized in {
        "UNLOCATED",
        "NEAR_PROPERTY",
        "NEARBY",
        "OUTSIDE_PROPERTY_AREA",
    }:
        return normalized
    return "UNLOCATED"


def _upper_or_default(value: str | None, default: str) -> str:
    return value.upper() if value else default


def _date_text(value: dt.date | None) -> str | None:
    return value.isoformat() if value else None


def _date_time_text(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def _number(value: Decimal | float | int | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _skipped_counts(objects: Iterable[str]) -> dict[str, int]:
    selected = set(objects)
    skipped: dict[str, int] = {}
    if "opportunity_zone" not in selected:
        return skipped
    skipped["opportunity_zone"] = 0
    return skipped
