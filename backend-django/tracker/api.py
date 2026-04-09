"""
Django Ninja API entry point.

Registers all routers under /api/ prefix, matching the existing FastAPI
URL structure so the frontend api.ts client works without changes.
"""
import asyncio
import json as json_mod
from datetime import date, datetime
from typing import Optional

from django.conf import settings
from django.db import models
from django.db.models import Count, Q, Avg, Min, Max, F, Value
from django.http import HttpResponse, StreamingHttpResponse, FileResponse
from ninja import NinjaAPI, Router, Query, File, UploadedFile

from tracker.models import Property, Communication, ImportBatch
from tracker.schemas import (
    PropertyCreate, PropertyUpdate, PropertyResponse,
    StatsResponse, ImportResult, BatchUpdateRequest,
    CommunicationCreate, CommunicationUpdate, CommunicationResponse,
    RESOLVED_FINDINGS,
)
from tracker.services.csv_parser import parse_csv_text
from tracker.services.exporter import (
    export_properties_csv, export_inspection_list_csv, generate_summary_report,
)
from tracker.services.enrichment import (
    apply_priority_scores, filter_by_contact,
    haversine_clusters, summarize_buyers, parse_closing_date,
)
from tracker.utils.address import build_address_key

api = NinjaAPI(
    title="GCLBA Compliance Tracker",
    version="2.0.0",
    urls_namespace="tracker",
)

# --- Routers ---
properties_router = Router(tags=["properties"])
imagery_router = Router(tags=["imagery"])
detection_router = Router(tags=["detection"])
comms_router = Router(tags=["communications"])
pipeline_router = Router(tags=["pipeline"])


# ============================================================
# Health / Root
# ============================================================

@api.get("/")
def root(request):
    return {
        "name": "GCLBA Compliance Tracker",
        "version": "2.0.0",
        "endpoints": {
            "properties": "/api/properties",
            "imagery": "/api/imagery",
            "detection": "/api/detection",
            "communications": "/api/communications",
            "pipeline": "/api/pipeline",
            "docs": "/api/docs",
        },
    }


@api.get("/health")
def health(request):
    return {"status": "ok"}


# ============================================================
# Properties Router
# ============================================================

def _property_to_dict(prop: Property, comm_count: int = 0) -> dict:
    """Convert a Property model instance to a dict matching PropertyResponse."""
    data = {
        "id": prop.id,
        "address": prop.address,
        "address_key": prop.address_key,
        "parcel_id": prop.parcel_id,
        "buyer_name": prop.buyer_name,
        "email": prop.email,
        "organization": prop.organization,
        "program": prop.program,
        "closing_date": prop.closing_date,
        "commitment": prop.commitment,
        "purchase_type": prop.purchase_type,
        "compliance_1st_attempt": prop.compliance_1st_attempt,
        "compliance_2nd_attempt": prop.compliance_2nd_attempt,
        "latitude": prop.latitude,
        "longitude": prop.longitude,
        "formatted_address": prop.formatted_address,
        "geocoded_at": prop.geocoded_at.isoformat() if prop.geocoded_at else None,
        "streetview_path": prop.streetview_path,
        "streetview_date": prop.streetview_date,
        "streetview_available": prop.streetview_available,
        "streetview_historical_path": prop.streetview_historical_path,
        "streetview_historical_date": prop.streetview_historical_date,
        "satellite_path": prop.satellite_path,
        "imagery_fetched_at": prop.imagery_fetched_at.isoformat() if prop.imagery_fetched_at else None,
        "detection_score": prop.detection_score,
        "detection_label": prop.detection_label,
        "detection_details": prop.detection_details or {},
        "detection_ran_at": prop.detection_ran_at.isoformat() if prop.detection_ran_at else None,
        "finding": prop.finding,
        "notes": prop.notes,
        "reviewed_at": prop.reviewed_at.isoformat() if prop.reviewed_at else None,
        "reviewed_by": prop.reviewed_by,
        "compliance_status": prop.compliance_status,
        "tax_status": prop.tax_status,
        "last_tax_payment": prop.last_tax_payment.isoformat() if prop.last_tax_payment else None,
        "tax_amount_owed": str(prop.tax_amount_owed) if prop.tax_amount_owed is not None else None,
        "homeowner_exemption": prop.homeowner_exemption,
        "outreach_attempts": prop.outreach_attempts,
        "last_outreach_date": prop.last_outreach_date.isoformat() if prop.last_outreach_date else None,
        "last_outreach_method": prop.last_outreach_method,
        "regrid_condition": prop.regrid_condition,
        "portal_survey_date": prop.portal_survey_date.isoformat() if prop.portal_survey_date else None,
        "import_batch": prop.import_batch,
        "created_at": prop.created_at.isoformat() if prop.created_at else "",
        "updated_at": prop.updated_at.isoformat() if prop.updated_at else "",
        "communication_count": comm_count,
    }
    return data


def _qs_to_dicts(qs) -> list[dict]:
    """Convert a queryset (annotated with communication_count) to dicts."""
    results = []
    for prop in qs:
        comm_count = getattr(prop, "communication_count", 0) or 0
        results.append(_property_to_dict(prop, comm_count))
    return results


def _resolved_values() -> set[str]:
    return RESOLVED_FINDINGS


@properties_router.get("/")
def list_properties(
    request,
    finding: str = None,
    detection: str = None,
    program: str = None,
    reviewed: bool = None,
    search: str = None,
    sort: str = "created_at",
    order: str = "desc",
    limit: int = 200,
    offset: int = 0,
):
    """List properties with optional filters."""
    qs = Property.objects.all()

    if finding:
        qs = qs.filter(finding=finding)
    if detection:
        qs = qs.filter(detection_label=detection)
    if program:
        qs = qs.filter(program=program)
    if reviewed is True:
        qs = qs.exclude(finding="").exclude(finding__isnull=True)
    elif reviewed is False:
        qs = qs.filter(Q(finding="") | Q(finding__isnull=True))
    if search:
        qs = qs.filter(
            Q(address__icontains=search) |
            Q(parcel_id__icontains=search) |
            Q(buyer_name__icontains=search) |
            Q(organization__icontains=search) |
            Q(email__icontains=search)
        )

    total = qs.count()

    allowed_sorts = ["created_at", "address", "detection_score", "reviewed_at", "program"]
    sort_col = sort if sort in allowed_sorts else "created_at"
    order_prefix = "-" if order.lower() != "asc" else ""

    qs = qs.annotate(
        communication_count=Count("communications")
    ).order_by(f"{order_prefix}{sort_col}")[offset:offset + limit]

    return {
        "properties": _qs_to_dicts(qs),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@properties_router.get("/map/all")
def get_map_properties(request, program: str = None, contact: str = "all"):
    """Return all geocoded properties with compliance priority scores."""
    qs = Property.objects.filter(latitude__isnull=False, longitude__isnull=False)
    if program:
        qs = qs.filter(program=program)

    rows = list(qs.values())
    prioritized = apply_priority_scores(rows)
    prioritized = filter_by_contact(prioritized, contact)
    prioritized.sort(key=lambda r: (-float(r.get("priority_score", 0.0)), r.get("address", "")))
    return {"count": len(prioritized), "properties": prioritized}


@properties_router.get("/buyers/summary")
def get_buyers_summary(request, program: str = None, contact: str = "all"):
    """Return buyer portfolio rollups for leadership reporting."""
    qs = Property.objects.all()
    if program:
        qs = qs.filter(program=program)

    rows = list(qs.values())
    prioritized = apply_priority_scores(rows)
    prioritized = filter_by_contact(prioritized, contact)
    buyers = summarize_buyers(prioritized)
    return {"count": len(buyers), "buyers": buyers}


@properties_router.get("/clusters")
def get_property_clusters(
    request,
    program: str = None,
    contact: str = "all",
    radius_miles: float = 0.35,
    min_points: int = 2,
):
    """Return Haversine clusters for geocoded properties."""
    qs = Property.objects.filter(latitude__isnull=False, longitude__isnull=False)
    if program:
        qs = qs.filter(program=program)

    rows = list(qs.values())
    prioritized = apply_priority_scores(rows)
    prioritized = filter_by_contact(prioritized, contact)
    clusters = haversine_clusters(prioritized, radius_miles=radius_miles, min_points=min_points)
    return {"count": len(clusters), "clusters": clusters}


@properties_router.get("/priority-queue")
def get_priority_queue(
    request,
    filter: str = "all",
    program: str = None,
    detection: str = None,
    search: str = None,
    sort: str = "priority",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
):
    """Return properties sorted by composite compliance priority."""
    qs = Property.objects.all()

    if filter == "unreviewed":
        qs = qs.filter(Q(finding="") | Q(finding__isnull=True))
    elif filter == "inconclusive":
        qs = qs.filter(finding="inconclusive")
    elif filter == "resolved":
        qs = qs.filter(finding__in=_resolved_values())
    elif filter == "reviewed":
        qs = qs.exclude(finding="").exclude(finding__isnull=True)

    if program:
        qs = qs.filter(program=program)
    if detection:
        qs = qs.filter(detection_label=detection)
    if search:
        qs = qs.filter(
            Q(address__icontains=search) |
            Q(parcel_id__icontains=search) |
            Q(buyer_name__icontains=search) |
            Q(organization__icontains=search) |
            Q(email__icontains=search)
        )

    qs = qs.annotate(communication_count=Count("communications"))
    rows = _qs_to_dicts(qs)
    prioritized = apply_priority_scores(rows)

    descending = order.lower() != "asc"
    sort_key = sort.lower()
    if sort_key == "address":
        prioritized.sort(key=lambda r: r.get("address", "").lower(), reverse=descending)
    elif sort_key == "created_at":
        prioritized.sort(key=lambda r: r.get("created_at", ""), reverse=descending)
    elif sort_key == "detection_score":
        prioritized.sort(key=lambda r: float(r.get("detection_score") or 0.0), reverse=descending)
    else:
        prioritized.sort(
            key=lambda r: (
                float(r.get("priority_score", 0.0)),
                float(r.get("detection_score") or 0.0),
                r.get("address", ""),
            ),
            reverse=True,
        )

    total = len(prioritized)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "properties": prioritized[offset:offset + limit],
    }


@properties_router.get("/stats/summary")
def get_stats(request):
    """Get aggregate statistics for the dashboard."""
    total = Property.objects.count()
    reviewed = Property.objects.exclude(finding="").exclude(finding__isnull=True).count()
    resolved = Property.objects.filter(finding__in=_resolved_values()).count()
    needs_inspection = Property.objects.filter(finding="inconclusive").count()
    inspection_candidates = Property.objects.filter(
        Q(finding="inconclusive") |
        Q(detection_label__in=["likely_vacant", "likely_demolished"])
    ).count()
    geocoded = Property.objects.filter(latitude__isnull=False).count()
    imagery_fetched = Property.objects.filter(imagery_fetched_at__isnull=False).count()
    detection_ran = Property.objects.filter(detection_ran_at__isnull=False).count()

    by_finding = dict(
        Property.objects.exclude(finding="").exclude(finding__isnull=True)
        .values_list("finding").annotate(n=Count("id")).order_by()
    )
    by_program = dict(
        Property.objects.values_list("program").annotate(n=Count("id")).order_by()
    )
    by_detection = dict(
        Property.objects.exclude(detection_label="").exclude(detection_label__isnull=True)
        .values_list("detection_label").annotate(n=Count("id")).order_by()
    )
    unreviewed_by_detection = dict(
        Property.objects.filter(Q(finding="") | Q(finding__isnull=True))
        .exclude(detection_label="").exclude(detection_label__isnull=True)
        .values_list("detection_label").annotate(n=Count("id")).order_by()
    )
    by_compliance_status = dict(
        Property.objects.values_list("compliance_status").annotate(n=Count("id")).order_by()
    )

    return {
        "total": total,
        "unreviewed": total - reviewed,
        "reviewed": reviewed,
        "resolved": resolved,
        "needs_inspection": needs_inspection,
        "inspection_candidates": inspection_candidates,
        "geocoded": geocoded,
        "imagery_fetched": imagery_fetched,
        "detection_ran": detection_ran,
        "by_finding": by_finding,
        "by_program": {k or "Unknown": v for k, v in by_program.items()},
        "by_detection": by_detection,
        "unreviewed_by_detection": unreviewed_by_detection,
        "by_compliance_status": by_compliance_status,
        "percent_reviewed": round(reviewed / total * 100, 1) if total > 0 else 0,
    }


@properties_router.post("/")
def create_property(request, payload: PropertyCreate):
    """Create a new property."""
    prop = Property.objects.create(
        address=payload.address,
        address_key=build_address_key(payload.address),
        parcel_id=payload.parcel_id,
        buyer_name=payload.buyer_name,
        program=payload.program,
        closing_date=payload.closing_date,
        commitment=payload.commitment,
        email=payload.email,
        organization=payload.organization,
        purchase_type=payload.purchase_type,
        compliance_1st_attempt=payload.compliance_1st_attempt,
        compliance_2nd_attempt=payload.compliance_2nd_attempt,
        streetview_historical_path=payload.streetview_historical_path,
        streetview_historical_date=payload.streetview_historical_date,
    )
    return _property_to_dict(prop)


@properties_router.post("/batch-update")
def batch_update_properties(request, payload: BatchUpdateRequest):
    """Batch update finding for multiple properties at once."""
    now = datetime.now()
    updated = 0
    for pid in payload.property_ids:
        update_fields = {"finding": payload.finding, "reviewed_at": now if payload.finding else None}
        Property.objects.filter(pk=pid).update(**update_fields)
        if payload.notes:
            prop = Property.objects.filter(pk=pid).first()
            if prop:
                existing = prop.notes or ""
                prop.notes = f"{existing}\n{payload.notes}".strip() if existing else payload.notes
                prop.save(update_fields=["notes"])
        updated += 1
    return {"updated": updated}


@properties_router.post("/import")
def import_csv(request, file: UploadedFile = File(None), text: str = ""):
    """Import properties from CSV file or pasted text."""
    if file:
        content = file.read().decode("utf-8-sig")
        filename = file.name or "upload.csv"
    elif text:
        content = text
        filename = "pasted_text"
    else:
        return api.create_response(request, {"detail": "Provide a file or text"}, status=400)

    properties, errors, batch_id = parse_csv_text(content, filename)

    if not properties and errors:
        return api.create_response(
            request, {"detail": f"Parse errors: {'; '.join(errors[:5])}"}, status=400
        )

    total_rows = len(properties) + len(errors)

    ImportBatch.objects.create(batch_id=batch_id, filename=filename, row_count=total_rows)

    inserted = 0
    updated = 0
    for prop in properties:
        try:
            existing = _find_existing_property(prop)
            if existing:
                _merge_import_property(existing, prop, batch_id)
                updated += 1
            else:
                Property.objects.create(
                    address=prop.address,
                    address_key=build_address_key(prop.address),
                    parcel_id=prop.parcel_id,
                    buyer_name=prop.buyer_name,
                    program=prop.program,
                    closing_date=prop.closing_date,
                    commitment=prop.commitment,
                    email=prop.email,
                    organization=prop.organization,
                    purchase_type=prop.purchase_type,
                    compliance_1st_attempt=prop.compliance_1st_attempt,
                    compliance_2nd_attempt=prop.compliance_2nd_attempt,
                    streetview_historical_path=prop.streetview_historical_path,
                    streetview_historical_date=prop.streetview_historical_date,
                    import_batch=batch_id,
                )
                inserted += 1
        except Exception as e:
            errors.append(f"Insert error for {prop.address}: {str(e)}")

    return {
        "batch_id": batch_id,
        "total_rows": total_rows,
        "imported": inserted + updated,
        "inserted": inserted,
        "updated": updated,
        "skipped": len(errors),
        "errors": errors[:10],
    }


def _find_existing_property(prop: PropertyCreate) -> Optional[Property]:
    """Find an existing property by parcel_id or address_key."""
    parcel_id = (prop.parcel_id or "").strip()
    if parcel_id:
        match = Property.objects.filter(parcel_id=parcel_id).first()
        if match:
            return match

    address_key = build_address_key(prop.address)
    if not address_key:
        return None

    return Property.objects.filter(address_key=address_key).first()


def _merge_import_property(existing: Property, prop: PropertyCreate, batch_id: str):
    """Merge new CSV data into an existing property (fill empty fields)."""
    merge_fields = [
        ("address", prop.address),
        ("parcel_id", prop.parcel_id),
        ("buyer_name", prop.buyer_name),
        ("program", prop.program),
        ("closing_date", prop.closing_date),
        ("commitment", prop.commitment),
        ("email", prop.email),
        ("organization", prop.organization),
        ("purchase_type", prop.purchase_type),
        ("compliance_1st_attempt", prop.compliance_1st_attempt),
        ("compliance_2nd_attempt", prop.compliance_2nd_attempt),
        ("streetview_historical_path", prop.streetview_historical_path),
        ("streetview_historical_date", prop.streetview_historical_date),
    ]
    changed = False
    for field_name, new_value in merge_fields:
        if new_value and not getattr(existing, field_name):
            setattr(existing, field_name, new_value)
            changed = True

    if prop.address:
        existing.address_key = build_address_key(prop.address)
        changed = True

    existing.import_batch = batch_id
    if changed:
        existing.save()


# --- Export endpoints ---

@properties_router.get("/export/csv")
def export_csv(
    request,
    finding: str = None,
    detection: str = None,
    program: str = None,
    contact: str = "all",
    search: str = None,
):
    """Export properties to CSV."""
    qs = Property.objects.all()
    if finding:
        qs = qs.filter(finding=finding)
    if detection:
        qs = qs.filter(detection_label=detection)
    if program:
        qs = qs.filter(program=program)
    if search:
        qs = qs.filter(
            Q(address__icontains=search) |
            Q(parcel_id__icontains=search) |
            Q(buyer_name__icontains=search) |
            Q(organization__icontains=search) |
            Q(email__icontains=search)
        )
    qs = qs.order_by("address")
    rows = list(qs.values())

    if contact != "all":
        rows = apply_priority_scores(rows)
        rows = filter_by_contact(rows, contact)

    csv_text = export_properties_csv(rows)
    response = HttpResponse(csv_text, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="compliance-export-{datetime.now().strftime("%Y%m%d")}.csv"'
    return response


@properties_router.get("/export/resolved")
def export_resolved(request):
    """Export desk-resolved properties."""
    qs = Property.objects.filter(finding__in=_resolved_values()).order_by("address")
    csv_text = export_properties_csv(list(qs.values()))
    response = HttpResponse(csv_text, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="resolved-properties-{datetime.now().strftime("%Y%m%d")}.csv"'
    return response


@properties_router.get("/export/inspection-list")
def export_inspection_list(request):
    """Export properties needing physical inspection."""
    qs = Property.objects.filter(
        Q(finding="inconclusive") |
        Q(detection_label__in=["likely_vacant", "likely_demolished"])
    ).order_by("-detection_score")
    csv_text = export_inspection_list_csv(list(qs.values()))
    response = HttpResponse(csv_text, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="inspection-list-{datetime.now().strftime("%Y%m%d")}.csv"'
    return response


@properties_router.get("/export/summary")
def export_summary(request):
    """Generate a text summary report."""
    stats = get_stats(request)
    report = generate_summary_report(stats)
    return HttpResponse(report, content_type="text/plain")


# Path-parameter routes must come after all static /properties/* routes
# so Django Ninja doesn't match "import", "export", etc. as {property_id}.

@properties_router.get("/{property_id}")
def get_property(request, property_id: int):
    """Get a single property with communication count."""
    try:
        prop = Property.objects.annotate(
            communication_count=Count("communications")
        ).get(pk=property_id)
    except Property.DoesNotExist:
        return api.create_response(request, {"detail": "Property not found"}, status=404)
    return _property_to_dict(prop, prop.communication_count)


@properties_router.patch("/{property_id}")
def update_property(request, property_id: int, payload: PropertyUpdate):
    """Partial update a property."""
    try:
        prop = Property.objects.get(pk=property_id)
    except Property.DoesNotExist:
        return api.create_response(request, {"detail": "Property not found"}, status=404)

    update_data = payload.dict(exclude_none=True)
    if not update_data:
        return api.create_response(request, {"detail": "No fields to update"}, status=400)

    for field, value in update_data.items():
        setattr(prop, field, value)

    if "address" in update_data:
        prop.address_key = build_address_key(update_data["address"])
    if "finding" in update_data:
        prop.reviewed_at = datetime.now() if update_data["finding"] else None

    prop.save()
    comm_count = prop.communications.count()
    return _property_to_dict(prop, comm_count)


@properties_router.delete("/{property_id}")
def delete_property(request, property_id: int):
    """Delete a property."""
    deleted_count, _ = Property.objects.filter(pk=property_id).delete()
    return {"deleted": deleted_count > 0}


# ============================================================
# Imagery Router
# ============================================================

@imagery_router.get("/status")
def imagery_status(request):
    """Check if Google Maps API is configured."""
    key = settings.GOOGLE_MAPS_API_KEY
    return {
        "configured": bool(key),
        "key_preview": key[:8] + "..." if key else None,
    }


@imagery_router.post("/geocode-batch")
async def geocode_batch(request, limit: int = 50):
    """Geocode all un-geocoded properties."""
    from tracker.services.geocoder import batch_geocode as _batch_geocode
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _get_rows():
        return list(
            Property.objects.filter(latitude__isnull=True)
            .values("id", "address")[:limit]
        )

    rows = await _get_rows()
    if not rows:
        return {"geocoded": 0, "message": "All properties already geocoded"}

    addresses = [row["address"] for row in rows]
    results = await _batch_geocode(addresses)

    geocoded = 0

    @sync_to_async
    def _update(row_id, result):
        Property.objects.filter(pk=row_id).update(
            latitude=result.lat,
            longitude=result.lng,
            formatted_address=result.formatted_address,
            geocoded_at=datetime.now(),
        )

    for row in rows:
        result = results.get(row["address"])
        if result:
            await _update(row["id"], result)
            geocoded += 1

    return {"geocoded": geocoded, "total_attempted": len(rows)}


@imagery_router.post("/fetch-batch")
async def fetch_batch_imagery(request, limit: int = 25):
    """Fetch imagery for all geocoded properties without images."""
    from tracker.services.imagery import batch_fetch_imagery as _batch_fetch
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _get_rows():
        return list(
            Property.objects.filter(latitude__isnull=False, imagery_fetched_at__isnull=True)
            .values("id", "address", "latitude", "longitude")[:limit]
        )

    rows = await _get_rows()
    if not rows:
        return {"fetched": 0, "message": "All geocoded properties already have imagery"}

    results = await _batch_fetch(rows)
    fetched = 0

    @sync_to_async
    def _update(prop_id, result):
        Property.objects.filter(pk=prop_id).update(
            streetview_path=result.streetview_path,
            streetview_available=result.streetview_available,
            streetview_date=result.streetview_date,
            satellite_path=result.satellite_path,
            imagery_fetched_at=datetime.now(),
        )

    for prop_id, result in results.items():
        await _update(prop_id, result)
        fetched += 1

    return {"fetched": fetched, "total_attempted": len(rows)}


@imagery_router.post("/fetch-historical/{property_id}")
async def fetch_historical(request, property_id: int):
    """Fetch historical Street View imagery using closing date."""
    from tracker.services.imagery import fetch_historical_streetview
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _get_prop():
        return Property.objects.filter(pk=property_id).values(
            "address", "latitude", "longitude", "closing_date",
        ).first()

    row = await _get_prop()
    if not row:
        return api.create_response(request, {"detail": "Property not found"}, status=404)
    if row["latitude"] is None or row["longitude"] is None:
        return api.create_response(request, {"detail": "Property not geocoded yet"}, status=422)

    parsed = parse_closing_date(row["closing_date"] or "")
    if not parsed:
        return api.create_response(request, {"detail": "No usable closing date available"}, status=422)
    target_date = parsed.strftime("%Y-%m")

    path, available, actual_date = await fetch_historical_streetview(
        lat=row["latitude"], lng=row["longitude"],
        address=row["address"], target_date=target_date,
    )

    if available:
        @sync_to_async
        def _update():
            Property.objects.filter(pk=property_id).update(
                streetview_historical_path=path,
                streetview_historical_date=actual_date,
            )
        await _update()

    return {
        "property_id": property_id,
        "historical_available": available,
        "target_date": target_date,
        "actual_date": actual_date,
        "streetview_historical_path": path,
    }


@imagery_router.get("/image/{property_id}/{image_type}")
def get_image(request, property_id: int, image_type: str):
    """Serve a cached image file."""
    from pathlib import Path

    column_map = {
        "streetview": "streetview_path",
        "satellite": "satellite_path",
        "streetview_historical": "streetview_historical_path",
    }
    column = column_map.get(image_type)
    if not column:
        return api.create_response(
            request, {"detail": "image_type must be: streetview, satellite, streetview_historical"}, status=400,
        )

    prop = Property.objects.filter(pk=property_id).values(column).first()
    if not prop or not prop[column]:
        return api.create_response(request, {"detail": f"No {image_type} image"}, status=404)

    path = Path(prop[column])
    if not path.exists():
        return api.create_response(request, {"detail": "Image file not found on disk"}, status=404)

    return FileResponse(path.open("rb"), filename=path.name, content_type="image/jpeg")


# ============================================================
# Detection Router
# ============================================================

@detection_router.post("/analyze-batch")
async def analyze_batch(request, limit: int = 50):
    """Run detection on properties with imagery but no detection results."""
    from tracker.services.detector import batch_detect as _batch_detect
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _get_rows():
        return list(
            Property.objects.filter(imagery_fetched_at__isnull=False, detection_ran_at__isnull=True)
            .values("id", "streetview_path", "satellite_path")[:limit]
        )

    rows = await _get_rows()
    if not rows:
        return {"analyzed": 0, "message": "All properties with imagery already analyzed"}

    results = await _batch_detect(rows)
    analyzed = 0

    @sync_to_async
    def _update(prop_id, result):
        Property.objects.filter(pk=prop_id).update(
            detection_score=result.score,
            detection_label=result.label,
            detection_details=result.details,
            detection_ran_at=datetime.now(),
        )

    for prop_id, result in results.items():
        await _update(prop_id, result)
        analyzed += 1

    label_counts = {}
    for result in results.values():
        label_counts[result.label] = label_counts.get(result.label, 0) + 1

    return {"analyzed": analyzed, "total_attempted": len(rows), "results_summary": label_counts}


@detection_router.get("/summary")
def detection_summary(request):
    """Detection results summary across all properties."""
    from django.db.models import Avg, Min, Max
    results = (
        Property.objects.filter(detection_ran_at__isnull=False)
        .values("detection_label")
        .annotate(
            count=Count("id"),
            avg_score=Avg("detection_score"),
            min_score=Min("detection_score"),
            max_score=Max("detection_score"),
        )
    )
    pending = Property.objects.filter(
        detection_ran_at__isnull=True, imagery_fetched_at__isnull=False,
    ).count()

    return {
        "results": [
            {
                "label": r["detection_label"],
                "count": r["count"],
                "avg_score": round(r["avg_score"] or 0, 3),
                "min_score": round(r["min_score"] or 0, 3),
                "max_score": round(r["max_score"] or 0, 3),
            }
            for r in results
        ],
        "pending_analysis": pending,
    }


# ============================================================
# Communications Router
# ============================================================

@comms_router.get("/{property_id}")
def list_communications(request, property_id: int):
    """List all communications for a property."""
    comms = Communication.objects.filter(property_id=property_id).order_by("-created_at")
    return [
        {
            "id": c.id,
            "property_id": c.property_id,
            "method": c.method,
            "direction": c.direction,
            "date_sent": c.date_sent.isoformat() if c.date_sent else None,
            "subject": c.subject,
            "body": c.body,
            "response_received": c.response_received,
            "response_date": c.response_date.isoformat() if c.response_date else None,
            "response_notes": c.response_notes,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in comms
    ]


@comms_router.post("/")
def create_communication(request, payload: CommunicationCreate):
    """Log a communication attempt."""
    comm = Communication.objects.create(
        property_id=payload.property_id,
        method=payload.method,
        direction=payload.direction,
        date_sent=payload.date_sent or date.today(),
        subject=payload.subject,
        body=payload.body,
    )
    return {
        "id": comm.id,
        "property_id": comm.property_id,
        "method": comm.method,
        "direction": comm.direction,
        "date_sent": comm.date_sent.isoformat() if comm.date_sent else None,
        "subject": comm.subject,
        "body": comm.body,
        "response_received": comm.response_received,
        "response_date": None,
        "response_notes": comm.response_notes,
        "created_at": comm.created_at.isoformat() if comm.created_at else None,
    }


@comms_router.patch("/{comm_id}")
def update_communication(request, comm_id: int, payload: CommunicationUpdate):
    """Update a communication (e.g., mark response received)."""
    try:
        comm = Communication.objects.get(pk=comm_id)
    except Communication.DoesNotExist:
        return api.create_response(request, {"detail": "Communication not found"}, status=404)

    update_data = payload.dict(exclude_none=True)
    if not update_data:
        return api.create_response(request, {"detail": "No fields to update"}, status=400)

    for field, value in update_data.items():
        setattr(comm, field, value)
    comm.save()

    return {
        "id": comm.id,
        "property_id": comm.property_id,
        "method": comm.method,
        "direction": comm.direction,
        "date_sent": comm.date_sent.isoformat() if comm.date_sent else None,
        "subject": comm.subject,
        "body": comm.body,
        "response_received": comm.response_received,
        "response_date": comm.response_date.isoformat() if comm.response_date else None,
        "response_notes": comm.response_notes,
        "created_at": comm.created_at.isoformat() if comm.created_at else None,
    }


# ============================================================
# Pipeline Router
# ============================================================

@pipeline_router.post("/process")
async def run_pipeline(
    request,
    geocode: bool = True,
    fetch_images: bool = True,
    run_detection: bool = True,
    limit: int = 0,
    process_all: bool = False,
):
    """Run the full processing pipeline."""
    from tracker.services.pipeline import run_pipeline as _run_pipeline
    return await _run_pipeline(
        geocode=geocode,
        fetch_images=fetch_images,
        run_detection_step=run_detection,
        limit=limit or settings.PIPELINE_BATCH_SIZE,
        process_all=process_all,
    )


@pipeline_router.post("/process-stream")
async def run_pipeline_stream(
    request,
    geocode: bool = True,
    fetch_images: bool = True,
    run_detection: bool = True,
    limit: int = 0,
    process_all: bool = False,
):
    """Stream pipeline progress via Server-Sent Events."""
    from tracker.services.pipeline import run_pipeline as _run_pipeline

    async def event_generator():
        def sse(data: dict) -> str:
            return f"data: {json_mod.dumps(data)}\n\n"

        event_queue: asyncio.Queue[dict] = asyncio.Queue()

        async def emit(event: dict):
            await event_queue.put(event)

        task = asyncio.create_task(
            _run_pipeline(
                geocode=geocode,
                fetch_images=fetch_images,
                run_detection_step=run_detection,
                limit=limit or settings.PIPELINE_BATCH_SIZE,
                process_all=process_all,
                emitter=emit,
            )
        )
        try:
            while True:
                if task.done() and event_queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.25)
                    yield sse(event)
                except asyncio.TimeoutError:
                    continue

            result = await task
            yield sse({"step": "complete", "status": "done", "totals": result.get("totals", {})})
        except Exception as exc:
            if not task.done():
                task.cancel()
            yield sse({"step": "error", "status": "failed", "message": str(exc)})

    return StreamingHttpResponse(event_generator(), content_type="text/event-stream")


# ============================================================
# Register Routers
# ============================================================

api.add_router("/api/properties", properties_router)
api.add_router("/api/imagery", imagery_router)
api.add_router("/api/detection", detection_router)
api.add_router("/api/communications", comms_router)
api.add_router("/api/pipeline", pipeline_router)
