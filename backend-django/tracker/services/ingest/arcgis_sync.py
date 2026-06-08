"""
Maps ArcGIS parcel features onto the tracker's Property model and records
ParcelValueSnapshot history plus a SyncRun audit row per run.

Split into a pure mapping layer (map_feature, esri_polygon_to_geojson,
compose_address) that does no DB work and is testable against the live layer,
and the DB layer (sync_source, seed_data_sources) that upserts and audits.

Merge policy: county-authoritative attributes (owner, forfeiture status,
geometry, class/use, values) always update; positional/address fields only
fill when empty, so a tracker-geocoded location is not degraded by the county
centroid.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from tracker.models import DataSource, ParcelValueSnapshot, Property, SyncRun
from tracker.utils.address import build_address_key, build_full_address, extract_parcel_id

from . import sources
from .arcgis_client import ArcGisClient, ArcGisError
from .arcgis_resolver import resolve_arcgis_layer

# Attributes the county owns; always refresh on sync.
ALWAYS_UPDATE = (
    "owner_of_record",
    "forfeiture_status",
    "forfeiture_status_year",
    "boundary_geojson",
    "property_class",
    "land_use",
    "assessed_value",
    "taxable_value",
)
# Positional/address fields; only fill when the tracker has none (do not overwrite
# a precise geocode with the parcel centroid).
FILL_IF_EMPTY = ("latitude", "longitude", "address", "formatted_address")


# --- pure mapping (no DB) ------------------------------------------------------
def esri_polygon_to_geojson(geometry: dict | None) -> dict | None:
    """esri polygon (rings) -> GeoJSON Polygon. First ring exterior, rest holes.

    Correct for the common single-ring parcel; multi-ring/hole precision is
    refined when contiguity neighborhood definitions are built (KNN uses the
    centroid lat/lon, not the polygon).
    """
    if not geometry:
        return None
    rings = geometry.get("rings")
    if not rings:
        return None
    return {"type": "Polygon", "coordinates": rings}


def compose_address(attrs: dict, parts: list[str]) -> str:
    chunks = []
    for part in parts:
        value = attrs.get(part)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            chunks.append(text)
    return " ".join(chunks).strip()


def map_feature(feature: dict, config: dict) -> dict | None:
    """ArcGIS feature -> normalized field dict (no DB). None when no parcel id."""
    attrs = feature.get("attributes") or {}
    field_map = config.get("field_map") or {}
    pid_field = config.get("parcel_id_field") or "PARIDSHORT"
    raw_pid = attrs.get(pid_field)
    parcel_id = extract_parcel_id(str(raw_pid)) if raw_pid else None
    if not parcel_id:
        return None

    mapped: dict = {"parcel_id": parcel_id}
    for src_field, dest_field in field_map.items():
        if dest_field == "parcel_id":
            continue
        value = attrs.get(src_field)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        mapped[dest_field] = value

    parts = config.get("address_part_fields") or []
    if parts:
        address = compose_address(attrs, parts)
        if address:
            mapped["address"] = address
            mapped["formatted_address"] = build_full_address(address)

    status_field = config.get("status_field")
    if status_field and attrs.get(status_field) not in (None, ""):
        mapped["forfeiture_status"] = str(attrs[status_field]).strip()
    status_year_field = config.get("status_year_field")
    if status_year_field and attrs.get(status_year_field) not in (None, ""):
        mapped["forfeiture_status_year"] = str(attrs[status_year_field]).strip()

    geometry = esri_polygon_to_geojson(feature.get("geometry"))
    if geometry:
        mapped["boundary_geojson"] = geometry

    oid_field = config.get("object_id_field") or "OBJECTID"
    mapped["_oid"] = attrs.get(oid_field)
    edit_field = config.get("edit_date_field")
    if edit_field:
        mapped["_cursor"] = attrs.get(edit_field)
    return mapped


def _config_from_source(source: DataSource) -> dict:
    cfg = source.config or {}
    return {
        "base_url": source.base_url,
        "layer_id": source.layer_id,
        "object_id_field": source.object_id_field or "OBJECTID",
        "edit_date_field": source.edit_date_field or "",
        "parcel_id_field": cfg.get("parcel_id_field", "PARIDSHORT"),
        "field_map": source.field_map or {},
        "address_part_fields": cfg.get("address_part_fields", []),
        "status_field": cfg.get("status_field"),
        "status_year_field": cfg.get("status_year_field"),
        "max_record_count": cfg.get("max_record_count", 2000),
        "out_sr": cfg.get("out_sr", 4326),
    }


# --- DB layer ------------------------------------------------------------------
@dataclass
class SyncResult:
    expected: int | None = None
    fetched: int = 0
    matched: int = 0
    updated: int = 0
    unmatched: int = 0
    max_oid: int = 0
    max_cursor: str = ""
    errors: list = field(default_factory=list)


def seed_data_sources(force: bool = False):
    """Upsert DataSource rows from sources.ALL_SEEDS.

    force=False (default) is create-only (get_or_create) so an operator's DB-side
    field_map edits survive; force=True refreshes rows from code.
    """
    created = updated = 0
    reserved = {"label", "kind", "base_url", "layer_id", "field_map", "edit_date_field", "object_id_field", "is_active", "key"}
    for seed in sources.ALL_SEEDS:
        defaults = {
            "label": seed.get("label", ""),
            "kind": seed.get("kind", "arcgis"),
            "base_url": seed.get("base_url", ""),
            "layer_id": str(seed.get("layer_id", "")),
            "field_map": seed.get("field_map", {}),
            "edit_date_field": seed.get("edit_date_field", ""),
            "object_id_field": seed.get("object_id_field", "OBJECTID"),
            "is_active": seed.get("is_active", True),
            "config": {k: v for k, v in seed.items() if k not in reserved},
        }
        if force:
            _, was_created = DataSource.objects.update_or_create(key=seed["key"], defaults=defaults)
        else:
            _, was_created = DataSource.objects.get_or_create(key=seed["key"], defaults=defaults)
        created += int(was_created)
        updated += int(not was_created)
    return created, updated


def get_active_source(key: str = "county_parcels") -> DataSource | None:
    return DataSource.objects.filter(key=key, is_active=True).first()


def resolve_and_store_source(key: str = "county_parcels") -> DataSource:
    seed = sources.seed_for(key)
    if seed is None:
        raise ValueError(f"Unknown source key: {key}")
    resolved = resolve_arcgis_layer(
        org_url=seed.get("org_url", "https://gccountymi.maps.arcgis.com"),
        search_query=seed.get("search_query", key),
        service_name_contains=seed.get("service_name_contains", ""),
    )
    defaults = {
        "label": seed.get("label", resolved.item_title),
        "kind": "arcgis",
        "base_url": resolved.base_url,
        "layer_id": resolved.layer_id,
        "field_map": resolved.field_map,
        "edit_date_field": resolved.edit_date_field,
        "object_id_field": resolved.object_id_field,
        "is_active": seed.get("is_active", True),
        "config": {
            **resolved.config,
            "org_url": seed.get("org_url", ""),
            "search_query": seed.get("search_query", ""),
            "service_name_contains": seed.get("service_name_contains", ""),
            "resolved_item_title": resolved.item_title,
            "resolved_layer_name": resolved.layer_name,
        },
    }
    source, _ = DataSource.objects.update_or_create(key=key, defaults=defaults)
    return source


def _apply_mapped(prop: Property, mapped: dict) -> bool:
    changed = False
    if not prop.parcel_id and mapped.get("parcel_id"):
        prop.parcel_id = mapped["parcel_id"]
        changed = True
    for name in FILL_IF_EMPTY:
        if name in mapped and not getattr(prop, name, None):
            setattr(prop, name, mapped[name])
            changed = True
    for name in ALWAYS_UPDATE:
        if name in mapped and getattr(prop, name, None) != mapped[name]:
            setattr(prop, name, mapped[name])
            changed = True
    if mapped.get("address") and not getattr(prop, "address_key", ""):
        prop.address_key = build_address_key(mapped["address"])
        changed = True
    return changed


def _write_snapshot(parcel_id: str, mapped: dict, observed_at, prop: Property | None) -> None:
    ParcelValueSnapshot.objects.update_or_create(
        parcel_id=parcel_id,
        observed_at=observed_at,
        source="county_arcgis",
        defaults={
            "property": prop,
            "assessed_value": mapped.get("assessed_value"),
            "taxable_value": mapped.get("taxable_value"),
            "forfeiture_status": mapped.get("forfeiture_status", ""),
            "raw": {"forfeiture_status_year": mapped.get("forfeiture_status_year", "")},
        },
    )


def sync_source(
    source: DataSource,
    *,
    page_limit: int | None = None,
    record_count: int | None = None,
    unmatched_policy: str | None = None,
) -> tuple[SyncRun, SyncResult]:
    """Pull from the source and upsert into Property; audit via SyncRun.

    The cursor (OBJECTID high-water) advances to DataSource.last_cursor only after
    the loop completes, so a failed run re-pulls instead of skipping.
    """
    policy = unmatched_policy or sources.UNMATCHED_PARCEL_POLICY
    config = _config_from_source(source)
    run = SyncRun.objects.create(source=source, status="running")
    result = SyncResult()
    today = timezone.now().date()

    try:
        client = ArcGisClient(
            config["base_url"],
            config["layer_id"],
            object_id_field=config["object_id_field"],
            edit_date_field=config["edit_date_field"],
            max_record_count=config["max_record_count"],
            out_sr=config["out_sr"],
        )
        try:
            cursor = source.last_cursor if config["edit_date_field"] else int(source.last_cursor or 0)
            result.expected = client.count_since(cursor)
            if result.expected == 0:
                result.max_oid = int(source.last_cursor or 0) if not config["edit_date_field"] else 0
                result.max_cursor = source.last_cursor if config["edit_date_field"] else ""
            for feature in (
                []
                if result.expected == 0
                else client.iter_features(cursor, page_limit=page_limit, record_count=record_count)
            ):
                result.fetched += 1
                mapped = map_feature(feature, config)
                if not mapped:
                    continue
                oid = mapped.pop("_oid", None)
                edit_cursor = mapped.pop("_cursor", None)
                if isinstance(oid, int):
                    result.max_oid = max(result.max_oid, oid)
                if edit_cursor not in (None, ""):
                    result.max_cursor = str(edit_cursor)
                parcel_id = mapped["parcel_id"]

                with transaction.atomic():
                    prop = Property.objects.filter(parcel_id=parcel_id).first()
                    if prop is None and mapped.get("address"):
                        akey = build_address_key(mapped["address"])
                        if akey:
                            prop = Property.objects.filter(address_key=akey).first()

                    if prop is None and policy != "write":
                        result.unmatched += 1
                        _write_snapshot(parcel_id, mapped, today, prop=None)
                        continue

                    is_new = prop is None
                    if is_new:
                        prop = Property(parcel_id=parcel_id)
                    else:
                        result.matched += 1

                    changed = _apply_mapped(prop, mapped)
                    if is_new or changed:
                        prop.save()
                        result.updated += 1
                    _write_snapshot(parcel_id, mapped, today, prop=prop)
        finally:
            client.close()

        if config["edit_date_field"] and result.max_cursor:
            source.last_cursor = result.max_cursor
        elif result.max_oid:
            source.last_cursor = str(result.max_oid)
        source.last_synced_at = timezone.now()
        source.save(update_fields=["last_cursor", "last_synced_at", "updated_at"])
        run.status = "ok"
    except ArcGisError as exc:
        run.status = "failed"
        result.errors.append(str(exc))
    except Exception as exc:  # noqa: BLE001 - audit any failure, never silently
        run.status = "partial"
        result.errors.append(repr(exc))

    run.fetched = result.fetched
    run.matched = result.matched
    run.updated = result.updated
    run.unmatched = result.unmatched
    run.finished_at = timezone.now()
    run.detail = {
        "errors": result.errors,
        "max_oid": result.max_oid,
        "max_cursor": result.max_cursor,
        "expected": result.expected,
        "policy": policy,
    }
    run.save()
    return run, result
