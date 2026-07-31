"""
P6: supersede undated Google satellite rows when dated NAIP covers the parcel.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from tracker.models import Property, PropertyImageEvidence


@dataclass
class SupersedeResult:
    property_id: int
    superseded: int = 0
    created_legacy: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _ensure_legacy_satellite_row(prop: Property) -> tuple[PropertyImageEvidence | None, bool]:
    """Materialize Property.satellite_path as evidence so it can carry superseded_by."""
    path = (prop.satellite_path or "").strip()
    if not path:
        return None, False

    existing = (
        PropertyImageEvidence.objects.filter(
            property=prop,
            image_source="SATELLITE",
            capture_date="",
        )
        .order_by("id")
        .first()
    )
    if existing:
        return existing, False

    row = PropertyImageEvidence.objects.create(
        property=prop,
        image_source="SATELLITE",
        image_kind="AERIAL",
        capture_date="",
        capture_date_precision="",
        storage_key="",
        sha256="",
        pano_id="",
        source_license="LICENSED_DISPLAY_ONLY",
        attribution="Google Static Maps satellite",
        provider_record_id="legacy-satellite",
        image_url=path,
        thumbnail_url=path,
        metadata={
            "legacy_property_field": "satellite_path",
            "materialized_at": timezone.now().isoformat(),
        },
    )
    return row, True


def supersede_undated_satellite_for_property(prop: Property) -> SupersedeResult:
    result = SupersedeResult(property_id=prop.id)
    naip = (
        PropertyImageEvidence.objects.filter(
            property=prop,
            image_source="NAIP_AERIAL",
            superseded_by__isnull=True,
        )
        .exclude(capture_date="")
        .order_by("-capture_date", "-id")
        .first()
    )
    if not naip:
        result.skipped += 1
        return result

    legacy, created = _ensure_legacy_satellite_row(prop)
    if created:
        result.created_legacy = 1

    undated = list(
        PropertyImageEvidence.objects.filter(
            property=prop,
            image_source="SATELLITE",
            capture_date="",
            superseded_by__isnull=True,
        )
    )
    if not undated:
        result.skipped += 1
        return result

    with transaction.atomic():
        for row in undated:
            if row.id == naip.id:
                continue
            row.superseded_by = naip
            meta = dict(row.metadata or {})
            meta["superseded_at"] = timezone.now().isoformat()
            meta["superseded_reason"] = "undated_satellite_replaced_by_naip"
            row.metadata = meta
            row.save(update_fields=["superseded_by", "metadata", "updated_at"])
            result.superseded += 1

    if result.superseded == 0 and not created:
        result.skipped += 1
    return result


def supersede_undated_satellite_batch(properties) -> list[SupersedeResult]:
    return [supersede_undated_satellite_for_property(prop) for prop in properties]
