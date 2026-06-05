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

## Done: Phase 2 neighborhood-context compute (migration 0005)
- `NeighborhoodContextScore` model (LISA scores: z_score, spatial_lag, moran_cluster,
  moran_p, gi_star, neighbor_parcel_ids).
- `tracker/services/context/`: `signals.py` (tax_distress/sale_recency/compliance;
  assessed_value yields None until a source exists), `weights.py` (KNN default;
  Queen/Rook need geopandas), `lisa.py` (Local Moran + local z + Getis-Ord), `composite.py`.
- `compute_context_scores` command; `sync_county_parcels --recompute-context` post-sync trigger.
- New deps: libpysal, esda (installed); geopandas for contiguity (later).
- Validated: makemigrations 0005, manage.py check, and a synthetic LISA fixture
  (planted high-on-low outlier classifies HL, z=+6.0). DB upsert path deferred to
  the remote Postgres (no local DB), same as Phase 1.
- First signal is tax_distress (forfeiture Status), NOT assessed value (no open source).

## Done: Phase 4 compliance Slices A + B (migration 0006, commits 2616e74 + 4591567)
- Slice A: ComplianceCase / DeedRestriction / Benchmark / ComplianceObservation / CaseEvent
  + 5-category tagging; tracker/services/compliance/ cases.py (activity logger) + report.py
  (weekly report text/HTML, optional weasyprint PDF); generate_weekly_report command.
- Slice B: deadline.py escalation engine (consumes compliance_timing + Benchmarks -> case
  status, logs CaseEvent, NO ActionItem writes); evaluate_compliance_cases command.

## Next (Claude backend) - increasingly on the SHARED surface; coordinate with Codex
- Phase 4 Slice C verification rail. CLEAN (Claude-owned): city permits ingest
  (Building_Permits_Current_Year -> permit ComplianceObservations, reuses arcgis_client)
  and assessment-change detection (ParcelValueSnapshot deltas -> assessment_change
  observations). SHARED: buyer-photo EXIF GPS extraction touches the upload path
  (api.py / workflow_documents) that Codex's 74141c2 owns -> COORDINATE before editing.
- Cross-cutting GraphQL: expose NeighborhoodContextScore + compliance types + ingest status
  on graphql_schema.py. That file is SHARED (Codex added upload_property_document in 74141c2)
  -> coordinate before editing to avoid collision.
- 4b buyer self-service public surface (separate, narrow scoped endpoint).
