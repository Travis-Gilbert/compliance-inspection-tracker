"""
Remote verification rail (compliance spec): turn external signals into tagged
ComplianceObservations without a site visit.

- City building permits: the cleanest objective rehab signal. A permit on a parcel
  after its sale date is rehab activity. Reuses the ingest ArcGisClient.
- Assessment changes: a rise in assessed/taxable value between ParcelValueSnapshots
  is an investment signal (gated until a value source exists; the County layer
  carries none today, so this currently keys off forfeiture-status changes).

map_permit is pure (testable / dry-run); sync_building_permits and
detect_assessment_changes read and write the DB.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from tracker.services.ingest.arcgis_client import ArcGisClient, ArcGisError
from tracker.utils.address import extract_parcel_id

from .cases import ensure_case, log_observation

MONTH_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _permit_date(attrs: dict) -> dt.date | None:
    """Derive a date from the layer's Year + Month ("a) January") fields."""
    raw_year = attrs.get("Year")
    try:
        year = int(raw_year) if raw_year not in (None, "") else None
    except (TypeError, ValueError):
        year = None
    if not year:
        return None
    month_text = str(attrs.get("Month") or "").lower()
    month = next((num for name, num in MONTH_NUM.items() if name in month_text), 1)
    try:
        return dt.date(year, month, 1)
    except ValueError:
        return None


def map_permit(feature: dict, config: dict) -> dict | None:
    """Pure: permit feature -> normalized dict (no DB). None if no parcel id."""
    attrs = feature.get("attributes") or {}
    pid = extract_parcel_id(str(attrs.get(config.get("parcel_id_field", "Parcel_ID")) or ""))
    if not pid:
        return None
    return {
        "parcel_id": pid,
        "permit_date": _permit_date(attrs),
        "permit_key": f"permit:{attrs.get('Permit__') or attrs.get('ID') or attrs.get('OBJECTID')}",
        "category": attrs.get("Category"),
        "value": attrs.get("Value_of_Permit"),
        "lat": attrs.get("Lat"),
        "lon": attrs.get("Long"),
        "comments": attrs.get("Comments"),
    }


def sync_building_permits(source, *, page_limit=None, record_count=None):
    """Pull permits and create permit ComplianceObservations on matching cases. (DB)"""
    from tracker.models import Property, SyncRun

    cfg = source.config or {}
    run = SyncRun.objects.create(source=source, status="running")
    fetched = matched = created = 0
    errors: list[str] = []
    today = timezone.now().date()
    try:
        client = ArcGisClient(
            source.base_url,
            source.layer_id,
            object_id_field=source.object_id_field or "OBJECTID",
            max_record_count=cfg.get("max_record_count", 2000),
        )
        try:
            for feature in client.iter_features(
                int(source.last_cursor or 0), page_limit=page_limit, record_count=record_count
            ):
                fetched += 1
                permit = map_permit(feature, cfg)
                if not permit:
                    continue
                prop = Property.objects.filter(parcel_id=permit["parcel_id"]).first()
                if not prop:
                    continue
                matched += 1
                case = ensure_case(prop)
                permit_date = permit["permit_date"]
                if case.sale_date and permit_date and permit_date < case.sale_date:
                    continue  # pre-sale permit is not a rehab signal
                if case.observations.filter(kind="permit", artifact_ref=permit["permit_key"]).exists():
                    continue  # de-dupe by permit id
                log_observation(
                    case,
                    kind="permit",
                    source="city_permits",
                    category_tag="oversight_enforcement",
                    observed_at=dt.datetime.combine(permit_date or today, dt.time.min),
                    artifact_ref=permit["permit_key"],
                    geo={"lat": permit["lat"], "lon": permit["lon"]},
                    exif={"category": permit["category"], "value": permit["value"], "comments": permit["comments"]},
                    created_by="permit_ingest",
                )
                created += 1
        finally:
            client.close()
        run.status = "ok"
    except ArcGisError as exc:
        run.status = "failed"
        errors.append(str(exc))
    except Exception as exc:  # noqa: BLE001 - audit any failure
        run.status = "partial"
        errors.append(repr(exc))

    run.fetched = fetched
    run.matched = matched
    run.updated = created
    run.finished_at = timezone.now()
    run.detail = {"errors": errors, "created_observations": created}
    run.save()
    return run, {"fetched": fetched, "matched": matched, "created": created, "errors": errors}


def detect_assessment_changes(*, parcel_ids=None):
    """Create assessment_change observations from value/status deltas across the two
    latest ParcelValueSnapshots per parcel. (DB)

    The County layer carries no assessed value yet, so the populated delta today is
    forfeiture_status; assessed/taxable deltas activate when a value source exists.
    """
    from tracker.models import ParcelValueSnapshot, Property

    created = 0
    qs = ParcelValueSnapshot.objects.order_by("parcel_id", "-observed_at")
    if parcel_ids:
        qs = qs.filter(parcel_id__in=list(parcel_ids))

    by_parcel: dict[str, list] = {}
    for snap in qs:
        by_parcel.setdefault(snap.parcel_id, []).append(snap)

    for parcel_id, snaps in by_parcel.items():
        if len(snaps) < 2:
            continue
        latest, prev = snaps[0], snaps[1]
        changed = []
        if latest.assessed_value is not None and prev.assessed_value is not None and latest.assessed_value != prev.assessed_value:
            changed.append(f"assessed {prev.assessed_value} -> {latest.assessed_value}")
        if (latest.forfeiture_status or "") != (prev.forfeiture_status or ""):
            changed.append(f"forfeiture {prev.forfeiture_status or 'none'} -> {latest.forfeiture_status or 'none'}")
        if not changed:
            continue
        prop = Property.objects.filter(parcel_id=parcel_id).first()
        if not prop:
            continue
        case = ensure_case(prop)
        key = f"assessment_change:{latest.observed_at.isoformat()}"
        if case.observations.filter(kind="assessment_change", artifact_ref=key).exists():
            continue
        log_observation(
            case,
            kind="assessment_change",
            source="regrid",
            category_tag="data_governance",
            observed_at=dt.datetime.combine(latest.observed_at, dt.time.min),
            artifact_ref=key,
            exif={"changes": changed},
            created_by="assessment_detector",
        )
        created += 1
    return {"created": created}
