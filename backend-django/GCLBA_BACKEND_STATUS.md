# GCLBA Backend Status (Claude lane)

Coordination note for Codex (frontend lane) and future sessions. The harness MCP
coordination write path is down this session, so this committed file + git log are
the substrate. Shared plan: the fork's
`docs/plans/gclba-compliance-system/master-plan-and-lanes.md`.

## Done: Phase 1 County ArcGIS spine (commit 949d672, branch main)
- Models + migration 0004: `DataSource`, `SyncRun`, `ParcelValueSnapshot`, `ServiceLineRecord`.
- `Property` fields: `assessed_value`, `taxable_value`, `owner_of_record`, `property_class`,
  `land_use`, `forfeiture_status`, `forfeiture_status_year`, `boundary_geojson`.
- `tracker/services/ingest/`: `sources.py` (resolved registry), `arcgis_client.py`
  (OBJECTID high-water diffing; layer 0 has no edit-date field), `arcgis_sync.py`
  (pure `map_feature` + DB `sync_source` + `seed_data_sources`).
- `management/commands/sync_county_parcels.py` (`--dry-run` maps live features with no DB).
- Validated: `makemigrations`, `manage.py check`, live `--dry-run` (real parcels, geometry).
This clears the fork README's "Missing" backend deps: ingest models, ingest package,
sync command, and parcel-polygon persistence (`boundary_geojson`).

## For your FE-006 (parcel document upload): the backend endpoint already exists
The topology spec says "dropzone posts files to a Django upload endpoint." That endpoint
is live:
  `POST {workflow_router}/properties/{property_id}/documents`
  multipart: `file`, `category=property_document`, `slot=manual_upload`, `description`
  -> `tracker.services.workflow_documents.save_uploaded_property_document` -> `Document` row.
It is parcel-scoped and generic. Wire the dropzone to it (REST upload is the spec path;
a Strawberry mutation can be added if you prefer GraphQL, but is not required).

## Findings that shape the build
- Assessed/taxable value: NO open per-parcel County source (only census-tract aggregates).
  Phase 2 context scores will base on `forfeiture_status` + sale recency; the assessed-value
  variant waits on a real source.
- `CountyRealProperty` layer 0 is ~232 County-owned / tax-reverted parcels (not the full
  county). `Status` (NCFD/CFD/...) is the forfeiture/foreclosure signal.

## Next (Claude backend)
- Phase 2: `tracker/services/context/` (signals, KNN weights, Local Moran via
  libpysal/esda) + `NeighborhoodContextScore` + `compute_context_scores`. New deps:
  geopandas/libpysal/esda. Next migration number is 0005.
- Phase 4: compliance reconciliation (CaseEvent + 5-category tagging + weekly report +
  remote verification rail). ComplianceCase.status is a separate axis from ActionItem;
  deadline_engine maps compliance_timing -> status, does not touch ActionItem rows.
