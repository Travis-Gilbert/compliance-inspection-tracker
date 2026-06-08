"""
Source registry for the GCLBA ingest spine.

Static SEED definitions for external data sources. Live mutable sync state
(last_cursor, last_synced_at) lives on the DataSource model; this module provides
the defaults used to seed/refresh those rows, plus per-instance behavior flags.
arcgis_sync reads the live field_map from the DataSource row (DB-authoritative, per
spec) so the County can rename a field without a code change.

Resolved 2026-06-05 against the Genesee County ArcGIS Online org 5ckbIY7K9TUKoseK.
See docs/GCLBA PLAN 6-5/MASTER-PLAN-AND-LANES.md for findings.
"""

from __future__ import annotations

# Unmatched-parcel policy: parcels arriving from the County that match no tracked
# Property. "write" creates each as a Property row (no compliance case), "skip"
# records only a value snapshot.
# GCLBA uses "write": SPEC-GCLBA-COUNTY-ARCGIS-INGEST states the neighborhood-
# context layer's condition signals (forfeiture status) come from this County
# feed, so the county tax-reverted parcels must exist as Property rows for the
# context layer to score them. "skip" would leave tax_distress empty and break
# that data flow. The spec sanctions "write them as parcels without a compliance
# case" for the GCLBA build.
UNMATCHED_PARCEL_POLICY = "write"

# Polite client identity for the shared (open-data) ArcGIS server.
USER_AGENT = "OurCivicAtlas-GCLBA/1.0 (Genesee County open-data ingest)"
REQUEST_DELAY_SECONDS = 0.3

# --- County parcel spine (VERIFIED live 2026-06-05) ----------------------------
COUNTY_PARCELS = {
    "key": "county_parcels",
    "label": "Genesee County Real Property (parcels, ownership, forfeiture status)",
    "kind": "arcgis",
    "base_url": "https://services2.arcgis.com/5ckbIY7K9TUKoseK/arcgis/rest/services/CountyRealProperty/FeatureServer",
    "layer_id": 0,
    "object_id_field": "OBJECTID",
    # Layer has no editDateField -> OBJECTID high-water diffing (spec fallback).
    "edit_date_field": "",
    "max_record_count": 2000,
    "out_sr": 4326,
    "org_url": "https://gccountymi.maps.arcgis.com",
    "search_query": "parcel",
    "service_name_contains": "CountyRealProperty",
    "parcel_id_field": "PARIDSHORT",
    # arcgis field -> Property field (direct upserts).
    "field_map": {
        "PARIDSHORT": "parcel_id",
        "OWNNAME": "owner_of_record",
        "Lat": "latitude",
        "Lon": "longitude",
    },
    # Address has no single source field; composed from these parts in arcgis_sync.
    "address_part_fields": ["PROPNUM", "PROPDIR", "PROPSTREET", "PROPCITY", "PROPZIP"],
    # Tax-distress condition signal (Michigan forfeiture/foreclosure status codes,
    # e.g. NCFD/CFD). Captured into ParcelValueSnapshot.raw + a Property column.
    "status_field": "Status",
    "status_year_field": "StatusYr",
    # NOTE: this layer carries NO assessed_value/taxable_value. Those Property fields
    # stay null from this source; assessed-value context is gated on a real source.
}

# --- Sibling layers (URLs known; FIELDS RESOLVED AT BUILD TIME, never guessed) --
# Resolve fields with `{base_url}/{layer_id}?f=json` before wiring, per the spec's
# anti-hardcoding rule. Activated in later phases.
LAND_BANK_PARCELS = {
    "key": "land_bank_parcels",
    "label": "GCLBA Land Bank Parcels",
    "kind": "arcgis",
    "base_url": "https://services2.arcgis.com/5ckbIY7K9TUKoseK/arcgis/rest/services/Land_Bank_Parcels/FeatureServer",
    "layer_id": 0,
    "org_url": "https://gccountymi.maps.arcgis.com",
    "search_query": "land bank parcels",
    "service_name_contains": "Land_Bank_Parcels",
    "field_map": {},
    "is_active": False,
}

BUILDING_PERMITS = {
    "key": "building_permits",
    "label": "Genesee County Building Permits (current year): rehab-activity signal",
    "kind": "arcgis",
    "base_url": "https://services2.arcgis.com/5ckbIY7K9TUKoseK/arcgis/rest/services/Building_Permits_Current_Year/FeatureServer",
    "layer_id": 0,
    "object_id_field": "OBJECTID",
    "edit_date_field": "",  # no edit-date field -> OBJECTID high-water diffing
    "max_record_count": 2000,
    "out_sr": 4326,
    # Permits create ComplianceObservations (not Property upserts). Date is derived
    # from Year + Month ("a) January"); permit after sale_date = rehab signal.
    "parcel_id_field": "Parcel_ID",
    "field_map": {},
    "is_active": True,
}

# Service-line infrastructure (flintpipemap / BlueConduit). Access form confirmed at
# build time; lowest priority (Phase 1 tail).
SERVICE_LINES = {
    "key": "servicelines",
    "label": "Flint service lines (flintpipemap / BlueConduit)",
    "kind": "http",
    "base_url": "",
    "field_map": {},
    "is_active": False,
}

# Seed set the spine relies on now; others activate as their phases land.
ACTIVE_SEEDS = [COUNTY_PARCELS]
ALL_SEEDS = [COUNTY_PARCELS, LAND_BANK_PARCELS, BUILDING_PERMITS, SERVICE_LINES]


def seed_for(key: str) -> dict | None:
    """Return the seed definition for a source key, or None."""
    for seed in ALL_SEEDS:
        if seed["key"] == key:
            return seed
    return None
