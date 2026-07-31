"""
NAIP aerial intake via Microsoft Planetary Computer STAC.

P1 of photo intake: for each geocoded parcel, discover every NAIP vintage,
window-read a fixed-footprint chip, store owned pixels, and upsert
PropertyImageEvidence rows (idempotent on property + source + capture_date).
"""
from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from tracker.models import Property, PropertyImageEvidence
from tracker.services.photo_storage import store_owned_bytes

logger = logging.getLogger(__name__)

DEFAULT_FOOTPRINT_METERS = 60.0
DEFAULT_OUTPUT_SIZE = 512
NAIP_ATTRIBUTION = "USDA NAIP via Microsoft Planetary Computer"
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


@dataclass
class NaipIntakeResult:
    property_id: int
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    vintages: list[str] = field(default_factory=list)


def _meters_to_degrees(lat: float, meters: float) -> tuple[float, float]:
    """Approximate (dlat, dlon) for a square box of `meters` side length."""
    dlat = meters / 111_320.0
    cos_lat = max(0.2, math.cos(math.radians(lat)))
    dlon = meters / (111_320.0 * cos_lat)
    return dlat / 2.0, dlon / 2.0


def _bbox_for_point(lat: float, lon: float, footprint_meters: float) -> list[float]:
    dlat, dlon = _meters_to_degrees(lat, footprint_meters)
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def _parse_item_date(item) -> tuple[str, str]:
    """Return (capture_date ISO day or empty, precision). Never invent dates."""
    props = getattr(item, "properties", None) or {}
    raw = props.get("datetime") or props.get("start_datetime") or ""
    if not raw:
        return "", ""
    text = str(raw).strip()
    if "T" in text:
        day = text.split("T", 1)[0]
        return day, "DAY"
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10], "DAY"
    if len(text) >= 7 and text[4] == "-":
        return text[:7], "MONTH"
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4], "YEAR"
    return "", ""


def _require_stac_stack():
    try:
        from pystac_client import Client  # noqa: F401
        import planetary_computer  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "NAIP intake requires optional deps: pip install pystac-client planetary-computer rasterio"
        ) from exc


def search_naip_items(lat: float, lon: float, *, footprint_meters: float):
    _require_stac_stack()
    from pystac_client import Client
    import planetary_computer

    catalog = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    bbox = _bbox_for_point(lat, lon, footprint_meters)
    search = catalog.search(collections=["naip"], bbox=bbox, max_items=50)
    items = list(search.items())
    items.sort(key=lambda i: (i.properties or {}).get("datetime") or "")
    return items


def _chip_via_planetary_computer_bbox(
    item_id: str,
    bbox: list[float],
    output_size: int,
) -> bytes:
    """Fetch a vintage-specific chip through Planetary Computer's data API (no direct Azure blob)."""
    import httpx
    from PIL import Image

    west, south, east, north = bbox
    url = (
        "https://planetarycomputer.microsoft.com/api/data/v1/item/"
        f"bbox/{west},{south},{east},{north}.png"
    )
    params = {
        "collection": "naip",
        "item": item_id,
        "assets": "image",
        "asset_bidx": "image|1,2,3",
        "width": str(output_size),
        "height": str(output_size),
    }
    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        if not response.content or len(response.content) < 100:
            raise ValueError("Planetary Computer bbox chip empty")
        # Normalize to JPEG for storage consistency.
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=90)
        return buf.getvalue()


def _chip_from_cog(href: str, bbox: list[float], output_size: int) -> bytes:
    """Windowed read of a COG into a JPEG chip. Requires rasterio."""
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    from PIL import Image

    with rasterio.open(href) as src:
        window = from_bounds(*bbox, transform=src.transform)
        data = src.read(
            indexes=list(range(1, min(4, src.count) + 1)),
            window=window,
            out_shape=(min(3, src.count), output_size, output_size),
            resampling=Resampling.bilinear,
            boundless=True,
            fill_value=0,
        )
    if data.ndim != 3 or data.shape[0] < 3:
        raise ValueError("NAIP asset did not yield RGB bands")
    rgb = np.transpose(data[:3], (1, 2, 0))
    if rgb.dtype != np.uint8:
        max_v = float(rgb.max()) if rgb.size else 1.0
        if max_v > 255:
            rgb = (rgb / max_v * 255.0).clip(0, 255).astype(np.uint8)
        else:
            rgb = rgb.clip(0, 255).astype(np.uint8)
    image = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _chip_via_usda_export(lat: float, lon: float, *, footprint_meters: float, output_size: int) -> bytes:
    """USDA APFO NAIP ImageServer export (latest mosaic — last-resort fallback)."""
    import httpx

    dlat, dlon = _meters_to_degrees(lat, footprint_meters)
    bbox = f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}"
    url = getattr(
        settings,
        "NAIP_EXPORT_URL",
        "https://gis.apfo.usda.gov/arcgis/rest/services/NAIP/USDA_CONUS_PRIME/ImageServer/exportImage",
    )
    params = {
        "bbox": bbox,
        "bboxSR": 4326,
        "imageSR": 4326,
        "size": f"{output_size},{output_size}",
        "format": "jpg",
        "f": "image",
    }
    with httpx.Client(timeout=60.0) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        if not response.content or len(response.content) < 100:
            raise ValueError("NAIP export returned empty image")
        return response.content


def render_naip_chip(
    item,
    *,
    lat: float,
    lon: float,
    footprint_meters: float,
    output_size: int,
) -> bytes:
    bbox = _bbox_for_point(lat, lon, footprint_meters)
    item_id = getattr(item, "id", "") or ""
    errors: list[str] = []

    if item_id:
        try:
            return _chip_via_planetary_computer_bbox(item_id, bbox, output_size)
        except Exception as exc:
            errors.append(f"pc-bbox: {exc}")
            logger.warning("PC bbox chip failed for %s: %s", item_id, exc)

    asset = (item.assets or {}).get("image") or (item.assets or {}).get("visual")
    href = getattr(asset, "href", None) if asset is not None else None
    if href:
        try:
            return _chip_from_cog(href, bbox, output_size)
        except Exception as exc:
            errors.append(f"cog: {exc}")
            logger.warning("COG chip failed for %s: %s", item_id or "?", exc)

    try:
        return _chip_via_usda_export(
            lat, lon, footprint_meters=footprint_meters, output_size=output_size,
        )
    except Exception as exc:
        errors.append(f"usda: {exc}")
        raise RuntimeError("; ".join(errors) or str(exc)) from exc



def upsert_naip_evidence(
    prop: Property,
    *,
    capture_date: str,
    capture_date_precision: str,
    stored,
    footprint_meters: float,
    provider_record_id: str = "",
    metadata: Optional[dict] = None,
) -> tuple[PropertyImageEvidence, bool]:
    """Return (row, created)."""
    defaults = {
        "image_kind": "AERIAL",
        "capture_date_precision": capture_date_precision,
        "storage_key": stored.storage_key,
        "sha256": stored.sha256,
        "image_url": stored.public_url,
        "thumbnail_url": stored.public_url,
        "source_license": "PUBLIC_DOMAIN",
        "attribution": NAIP_ATTRIBUTION,
        "provider_record_id": provider_record_id or capture_date,
        "footprint_meters": footprint_meters,
        "pano_id": "",
        "metadata": metadata or {},
    }
    with transaction.atomic():
        row, created = PropertyImageEvidence.objects.update_or_create(
            property=prop,
            image_source="NAIP_AERIAL",
            capture_date=capture_date,
            defaults=defaults,
        )
    return row, created


def intake_naip_for_property(
    prop: Property,
    *,
    footprint_meters: float | None = None,
    output_size: int | None = None,
    dry_run: bool = False,
) -> NaipIntakeResult:
    result = NaipIntakeResult(property_id=prop.id)
    if prop.latitude is None or prop.longitude is None:
        result.errors.append("property not geocoded")
        return result

    footprint = float(
        footprint_meters
        if footprint_meters is not None
        else getattr(settings, "NAIP_FOOTPRINT_METERS", DEFAULT_FOOTPRINT_METERS)
    )
    size = int(
        output_size
        if output_size is not None
        else getattr(settings, "NAIP_OUTPUT_SIZE", DEFAULT_OUTPUT_SIZE)
    )
    lat = float(prop.latitude)
    lon = float(prop.longitude)
    parcel_id = prop.parcel_id or f"property-{prop.id}"

    try:
        items = search_naip_items(lat, lon, footprint_meters=footprint)
    except Exception as exc:
        result.errors.append(f"STAC search failed: {exc}")
        return result

    if not items:
        result.skipped += 1
        result.errors.append("no NAIP items in footprint")
        return result

    seen_dates: set[str] = set()
    for item in items:
        capture_date, precision = _parse_item_date(item)
        if not capture_date:
            result.skipped += 1
            continue
        if capture_date in seen_dates:
            result.skipped += 1
            continue
        seen_dates.add(capture_date)
        result.vintages.append(capture_date)

        if dry_run:
            result.created += 1
            continue

        try:
            chip = render_naip_chip(
                item, lat=lat, lon=lon, footprint_meters=footprint, output_size=size,
            )
            stored = store_owned_bytes(
                chip,
                parcel_id=parcel_id,
                source="NAIP_AERIAL",
                capture_date=capture_date,
            )
            _row, created = upsert_naip_evidence(
                prop,
                capture_date=capture_date,
                capture_date_precision=precision,
                stored=stored,
                footprint_meters=footprint,
                provider_record_id=getattr(item, "id", "") or capture_date,
                metadata={
                    "stac_id": getattr(item, "id", ""),
                    "ingested_at": timezone.now().isoformat(),
                },
            )
            if created:
                result.created += 1
            else:
                result.updated += 1
        except Exception as exc:
            logger.exception("NAIP chip failed for property %s date %s", prop.id, capture_date)
            result.errors.append(f"{capture_date}: {exc}")

    return result


def intake_naip_batch(
    properties: Iterable[Property],
    *,
    footprint_meters: float | None = None,
    output_size: int | None = None,
    dry_run: bool = False,
) -> list[NaipIntakeResult]:
    return [
        intake_naip_for_property(
            prop,
            footprint_meters=footprint_meters,
            output_size=output_size,
            dry_run=dry_run,
        )
        for prop in properties
    ]
