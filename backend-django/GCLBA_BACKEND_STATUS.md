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

## Done: verification rail (Slice C, 7d93a3f) + GraphQL exposure
- Slice C: sync_building_permits (permit ComplianceObservations) + detect_assessment_changes.
- GraphQL: tracker/graphql_context.py merged via strawberry.tools.merge_types (graphql_schema.py
  gained only an import + the schema line, low collision). The fork can now query:
  contextScores(neighborhoodDef, signal, parcelIds) / contextScore(parcelId, ...);
  complianceCases(status, program) / complianceCase(parcelId) / caseEvents(parcelId);
  weeklyReport(weekOf). Codex Phase 3 viz can swap its synthetic fixture for live contextScores.

## Done: Property intelligence D7 import + GraphQL read model
- `Property.sources` stores scrubbed source-record dossiers from the private index.
- `SourceConflict` is the conflict ledger table; `CandidateProperty` is the compliance
  review queue for homes discovered from conflicts such as `owner_mismatch`.
- `import_index_dossiers <path.json>` imports gclba-index JSON, strips buyer/contact/private
  fields from source facts, and upserts properties, conflicts, and candidates.
- GraphQL now exposes `propertyIntelligence`, `sourceConflicts`, and `candidateProperties`
  for the GCLBA frontend. Validated with `manage.py test tracker.tests.test_graphql_api`
  and `manage.py check`.

## Done: Twenty D5/D6 live delivery and workspace polish
- `sync_twenty_crm --push` now uses a backend `TwentyClient` to deliver changed projection
  rows to Twenty custom-object REST endpoints. Full-inventory sync is the default.
- Delivery stores `twenty_record_id`, `twenty_url`, `last_synced_at`, and `last_error` on
  `TwentySyncRecord`; unchanged rows with a stored Twenty id are skipped on later pushes.
- `bootstrap_twenty_schema` creates/verifies the GCLBA custom objects, fields, views,
  navigation entries, and read-only role through Twenty's metadata API.
- Live Railway Backend has `TWENTY_BASE_URL`, `TWENTY_FRONTEND_URL`, and `TWENTY_API_KEY`
  configured. The key is not stored in this repo.
- Live Twenty workspace was bootstrapped and populated on 2026-07-08:
  798 `gclbaProperties`, 710 `gclbaOutreachRecords`, and 798
  `gclbaHomeQualityObservations`, with `TwentySyncRecord` at 2306 delivered, 0 errors,
  0 pending.
- Validated with `manage.py test tracker.tests.test_twenty_sync tracker.tests.test_twenty_schema`
  plus live Railway `sync_twenty_crm --push` and Twenty REST spot checks.

## Done: Property intelligence D9/D10 report and share package
- Weekly compliance reports now include computed Coverage and Discoveries lines from the
  same property-intelligence summary used by GraphQL.
- `generate_property_intelligence_share_package` exports the one-page plain-language share
  package as text, HTML, and PDF from current Django data.
- The generated report/share paths avoid em dashes in text and HTML.
- Validated with `manage.py test tracker.tests.test_property_intelligence_reporting`.

## Remaining
- Data/index: D1-D4 still need the separate private `gclba-index` service that embeds the
  pinned Datawave crates and emits the JSON imported by `import_index_dossiers`.
- Map: D8 still needs the frontend coverage layer and parcel-card provenance wired to the
  live GraphQL property-intelligence fields.
- Claude (small/optional): buyer-photo EXIF GPS extraction (shared upload path; coordinate before
  editing api.py/workflow_documents); 4b buyer self-service public surface (new narrow scoped
  endpoint); service-line sync (lowest priority, source not yet resolved); aerial/street-level
  change detection (spec marks these later refinements).
- Codex (frontend lane): Phase 3 context viz (design-gated) + live-swap to contextScores;
  Phase 5 remaining integration; deploy (separate GCLBA RustyRed + Vercel + retire portal) needs
  Travis go-ahead.
- End-to-end run of all syncs/compute/report needs the Railway Postgres (no local DB here); every
  unit was validated via makemigrations / check / live dry-run / SDL generation / pure-math tests.
