"""
Historical Street View enumeration (licensed pointers only).

P2 of photo intake: resolve nearby panoramas over time and store pano id +
provider date + heading toward the parcel. Never warehouse Google pixels.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from tracker.models import Property, PropertyImageEvidence

logger = logging.getLogger(__name__)

EARLIEST_YEAR = 2007


@dataclass(frozen=True)
class PanoPointer:
    pano_id: str
    capture_date: str
    capture_date_precision: str
    camera_lat: float | None = None
    camera_lng: float | None = None
    heading_degrees: float | None = None


@dataclass
class StreetHistoryResult:
    property_id: int
    created: int = 0
    updated: int = 0
    skipped: int = 0
    panos: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from camera (lat1,lon1) toward target (lat2,lon2)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _normalize_date(raw: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if not text:
        return "", ""
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10], "DAY"
    if len(text) >= 7 and text[4] == "-":
        return text[:7], "MONTH"
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4], "YEAR"
    return "", ""


def _metadata_url() -> str:
    return getattr(
        settings,
        "STREETVIEW_METADATA_URL",
        "https://maps.googleapis.com/maps/api/streetview/metadata",
    )


async def _fetch_metadata(
    client: httpx.AsyncClient,
    *,
    lat: float,
    lng: float,
    date: str | None = None,
    pano: str | None = None,
) -> dict:
    key = getattr(settings, "GOOGLE_MAPS_API_KEY", "") or ""
    if not key:
        return {"status": "REQUEST_DENIED", "error_message": "missing API key"}
    params: dict[str, str] = {"key": key, "source": "outdoor"}
    if pano:
        params["pano"] = pano
    else:
        params["location"] = f"{lat},{lng}"
    if date:
        params["date"] = date
    response = await client.get(_metadata_url(), params=params)
    if response.status_code != 200:
        return {"status": "HTTP_ERROR", "error_message": str(response.status_code)}
    return response.json()


def _pointer_from_metadata(data: dict, *, target_lat: float, target_lng: float) -> PanoPointer | None:
    if data.get("status") != "OK":
        return None
    pano_id = (data.get("pano_id") or "").strip()
    if not pano_id:
        return None
    capture_date, precision = _normalize_date(data.get("date") or "")
    loc = data.get("location") or {}
    cam_lat = loc.get("lat")
    cam_lng = loc.get("lng")
    heading = None
    if cam_lat is not None and cam_lng is not None:
        heading = bearing_degrees(float(cam_lat), float(cam_lng), target_lat, target_lng)
    return PanoPointer(
        pano_id=pano_id,
        capture_date=capture_date,
        capture_date_precision=precision,
        camera_lat=float(cam_lat) if cam_lat is not None else None,
        camera_lng=float(cam_lng) if cam_lng is not None else None,
        heading_degrees=heading,
    )


async def enumerate_panoramas(
    lat: float,
    lng: float,
    *,
    client: httpx.AsyncClient | None = None,
    year_start: int = EARLIEST_YEAR,
    year_end: int | None = None,
) -> list[PanoPointer]:
    """
    Enumerate historical panos by stepping metadata date queries.

    The Maps JS StreetViewService `time` array is the documented rich source;
    server-side Metadata API does not expose that array. Yearly (and mid-year)
    probes collect unique pano ids + provider dates without downloading pixels.
    """
    end = year_end or dt.date.today().year
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=20.0)
    found: dict[str, PanoPointer] = {}
    try:
        # Current coverage first (no date filter).
        current = await _fetch_metadata(http, lat=lat, lng=lng)
        pointer = _pointer_from_metadata(current, target_lat=lat, target_lng=lng)
        if pointer:
            found[pointer.pano_id] = pointer

        for year in range(year_start, end + 1):
            for month in (6, 1):
                date = f"{year:04d}-{month:02d}"
                data = await _fetch_metadata(http, lat=lat, lng=lng, date=date)
                pointer = _pointer_from_metadata(data, target_lat=lat, target_lng=lng)
                if pointer:
                    # Prefer the earlier-seen date if same pano; keep first.
                    found.setdefault(pointer.pano_id, pointer)
    finally:
        if owns_client:
            await http.aclose()

    return sorted(
        found.values(),
        key=lambda p: (p.capture_date or "", p.pano_id),
    )


def licensed_image_url(pano_id: str, *, heading: float | None = None) -> str:
    """Django proxy URL — no API key in Twenty payloads, no warehoused pixels."""
    backend = (getattr(settings, "GCLBA_BACKEND_PUBLIC_URL", "") or "").strip().rstrip("/")
    path = f"/api/imagery/pano/{pano_id}"
    if heading is not None:
        path = f"{path}?heading={heading:.1f}"
    if backend:
        return f"{backend}{path}"
    return path


def upsert_historical_pointer(prop: Property, pointer: PanoPointer) -> tuple[PropertyImageEvidence, bool]:
    source = "HISTORICAL_STREET_VIEW"
    # Newest dated pano can also be tagged as current street if it matches Property.streetview_date
    defaults = {
        "image_kind": "HISTORICAL_EXTERIOR",
        "capture_date": pointer.capture_date,
        "capture_date_precision": pointer.capture_date_precision,
        "storage_key": "",
        "sha256": "",
        "image_url": licensed_image_url(pointer.pano_id, heading=pointer.heading_degrees),
        "thumbnail_url": "",
        "source_license": "LICENSED_DISPLAY_ONLY",
        "attribution": "Google Street View",
        "provider_record_id": pointer.pano_id,
        "heading_degrees": pointer.heading_degrees,
        "footprint_meters": None,
        "metadata": {
            "camera_lat": pointer.camera_lat,
            "camera_lng": pointer.camera_lng,
            "enumerated_at": timezone.now().isoformat(),
        },
    }
    with transaction.atomic():
        row, created = PropertyImageEvidence.objects.update_or_create(
            property=prop,
            image_source=source,
            pano_id=pointer.pano_id,
            defaults=defaults,
        )
    return row, created


async def intake_street_history_for_property(
    prop: Property,
    *,
    dry_run: bool = False,
) -> StreetHistoryResult:
    result = StreetHistoryResult(property_id=prop.id)
    if prop.latitude is None or prop.longitude is None:
        result.errors.append("property not geocoded")
        return result
    if not getattr(settings, "GOOGLE_MAPS_API_KEY", ""):
        result.errors.append("GOOGLE_MAPS_API_KEY not configured")
        return result

    try:
        pointers = await enumerate_panoramas(float(prop.latitude), float(prop.longitude))
    except Exception as exc:
        result.errors.append(f"enumeration failed: {exc}")
        return result

    if not pointers:
        result.skipped += 1
        # Probe once without date to surface API key / billing errors clearly.
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                probe = await _fetch_metadata(
                    client, lat=float(prop.latitude), lng=float(prop.longitude),
                )
            status = probe.get("status") or "UNKNOWN"
            detail = probe.get("error_message") or probe.get("status") or "no panoramas found"
            if status != "OK":
                result.errors.append(f"Street View metadata {status}: {detail}")
            else:
                result.errors.append("no panoramas found")
        except Exception as exc:
            result.errors.append(f"no panoramas found ({exc})")
        return result

    for pointer in pointers:
        result.panos.append(pointer.pano_id)
        if dry_run:
            result.created += 1
            continue
        try:
            _row, created = upsert_historical_pointer(prop, pointer)
            if created:
                result.created += 1
            else:
                result.updated += 1
        except Exception as exc:
            logger.exception("Failed to upsert pano %s for property %s", pointer.pano_id, prop.id)
            result.errors.append(f"{pointer.pano_id}: {exc}")

    return result


async def intake_street_history_batch(
    properties: Iterable[Property],
    *,
    dry_run: bool = False,
) -> list[StreetHistoryResult]:
    results = []
    for prop in properties:
        results.append(await intake_street_history_for_property(prop, dry_run=dry_run))
    return results
