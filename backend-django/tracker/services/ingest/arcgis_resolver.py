"""
ArcGIS Online source discovery for the County ingest spine.

The sync uses DataSource rows at runtime. This resolver refreshes those rows from
the public ArcGIS Online org instead of requiring operators to hardcode a guessed
FeatureServer path.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


PARCEL_FIELD_CANDIDATES = ("PARIDSHORT", "Parcel_ID", "PARCELID", "PARCEL_ID", "PIN", "APN")
OWNER_FIELD_CANDIDATES = ("OWNNAME", "Owner", "OWNER", "OWNER_NAME")
LAT_FIELD_CANDIDATES = ("Lat", "LAT", "Latitude", "LATITUDE")
LON_FIELD_CANDIDATES = ("Lon", "LON", "Longitude", "LONGITUDE")
ASSESSED_FIELD_CANDIDATES = ("ASSESSED", "AssessedValue", "ASSESSED_VALUE", "SEV")
TAXABLE_FIELD_CANDIDATES = ("TAXABLE", "TaxableValue", "TAXABLE_VALUE")
STATUS_FIELD_CANDIDATES = ("Status", "STATUS", "FORFEITURE_STATUS")
STATUS_YEAR_FIELD_CANDIDATES = ("StatusYr", "STATUS_YEAR", "FORFEITURE_YEAR")
ADDRESS_PART_CANDIDATES = ("PROPNUM", "PROPDIR", "PROPSTREET", "PROPCITY", "PROPZIP")


@dataclass(frozen=True)
class ResolvedArcGisLayer:
    base_url: str
    layer_id: str
    object_id_field: str
    edit_date_field: str
    max_record_count: int
    field_map: dict[str, str]
    config: dict
    item_title: str
    layer_name: str


def _get_json(client: httpx.Client, url: str, params: dict) -> dict:
    response = client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(f"ArcGIS resolver error: {data['error']}")
    return data


def _field_names(fields: list[dict]) -> set[str]:
    return {str(field.get("name", "")).strip() for field in fields if field.get("name")}


def _first_field(field_names: set[str], candidates: tuple[str, ...]) -> str:
    for candidate in candidates:
        if candidate in field_names:
            return candidate
    lowered = {name.lower(): name for name in field_names}
    for candidate in candidates:
        found = lowered.get(candidate.lower())
        if found:
            return found
    return ""


def _object_id_field(layer_meta: dict) -> str:
    if layer_meta.get("objectIdField"):
        return str(layer_meta["objectIdField"])
    for field in layer_meta.get("fields", []):
        if field.get("type") == "esriFieldTypeOID" and field.get("name"):
            return str(field["name"])
    return "OBJECTID"


def _edit_date_field(layer_meta: dict) -> str:
    edit_info = layer_meta.get("editFieldsInfo") or {}
    if edit_info.get("editDateField"):
        return str(edit_info["editDateField"])
    fields = _field_names(layer_meta.get("fields", []))
    return _first_field(fields, ("EditDate", "last_edited_date", "LAST_EDITED_DATE"))


def _field_map(field_names: set[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for source, dest in (
        (_first_field(field_names, PARCEL_FIELD_CANDIDATES), "parcel_id"),
        (_first_field(field_names, OWNER_FIELD_CANDIDATES), "owner_of_record"),
        (_first_field(field_names, LAT_FIELD_CANDIDATES), "latitude"),
        (_first_field(field_names, LON_FIELD_CANDIDATES), "longitude"),
        (_first_field(field_names, ASSESSED_FIELD_CANDIDATES), "assessed_value"),
        (_first_field(field_names, TAXABLE_FIELD_CANDIDATES), "taxable_value"),
    ):
        if source:
            mapping[source] = dest
    return mapping


def resolve_arcgis_layer(
    *,
    org_url: str,
    search_query: str,
    service_name_contains: str = "",
    client: httpx.Client | None = None,
) -> ResolvedArcGisLayer:
    owns_client = client is None
    client = client or httpx.Client(timeout=60)
    try:
        org = org_url.rstrip("/")
        search = _get_json(
            client,
            f"{org}/sharing/rest/search",
            {"q": search_query, "f": "json", "num": 100},
        )
        items = [
            item
            for item in search.get("results", [])
            if item.get("type") == "Feature Service" and item.get("url")
        ]
        if service_name_contains:
            preferred = [
                item
                for item in items
                if service_name_contains.lower() in str(item.get("title", "")).lower()
                or service_name_contains.lower() in str(item.get("url", "")).lower()
            ]
            items = preferred or items

        for item in items:
            service_url = str(item["url"]).rstrip("/")
            service = _get_json(client, service_url, {"f": "json"})
            for layer in service.get("layers", []):
                layer_id = str(layer.get("id", ""))
                if not layer_id:
                    continue
                layer_meta = _get_json(client, f"{service_url}/{layer_id}", {"f": "json"})
                if layer_meta.get("geometryType") != "esriGeometryPolygon":
                    continue
                names = _field_names(layer_meta.get("fields", []))
                parcel_field = _first_field(names, PARCEL_FIELD_CANDIDATES)
                if not parcel_field:
                    continue
                status_field = _first_field(names, STATUS_FIELD_CANDIDATES)
                status_year_field = _first_field(names, STATUS_YEAR_FIELD_CANDIDATES)
                address_parts = [field for field in ADDRESS_PART_CANDIDATES if field in names]
                return ResolvedArcGisLayer(
                    base_url=service_url,
                    layer_id=layer_id,
                    object_id_field=_object_id_field(layer_meta),
                    edit_date_field=_edit_date_field(layer_meta),
                    max_record_count=int(layer_meta.get("maxRecordCount") or service.get("maxRecordCount") or 2000),
                    field_map=_field_map(names),
                    config={
                        "parcel_id_field": parcel_field,
                        "address_part_fields": address_parts,
                        "status_field": status_field,
                        "status_year_field": status_year_field,
                        "max_record_count": int(layer_meta.get("maxRecordCount") or 2000),
                        "out_sr": 4326,
                    },
                    item_title=str(item.get("title", "")),
                    layer_name=str(layer_meta.get("name", layer.get("name", ""))),
                )
        raise RuntimeError(f"No parcel polygon FeatureServer layer found for {search_query!r}")
    finally:
        if owns_client:
            client.close()
