# Unified Compliance Workbench Plan

## Purpose

This repository is the canonical compliance workbench. The current
`compliance-inspection-tracker` app owns the inspection, imagery, review,
import, export, and Django/PostGIS path. The older
`Compliance.Thelandbank.org` portal is reference material for workflow rules,
field shape, action queues, templates, and communication history.

The goal is to move the older portal's SOP compression into this repo without
reviving the older storage architecture. Staff should be able to see a
property, its buyer, program, due calculation, recommended next action,
communication history, and queue position from one Django/PostGIS-backed
workbench.

## Source Of Truth

Django/PostGIS is the source of truth for the workbench.

- `Property` remains the central spatial and inspection record.
- Program and buyer workflow concepts should be normalized around the current
  `Property` model instead of replacing it.
- Current-state rollup fields on `Property` should remain available for import,
  export, dashboards, and simple filtering.
- New normalized tables should be introduced gradually, with nullable links
  where existing data cannot be inferred safely.

## Storage Direction

S3-compatible storage is the target for binary and generated artifacts.

- Photos
- Documents
- Cached Street View and satellite imagery
- Export artifacts

PostGIS stores relational and spatial truth. Object storage stores files and
derived artifacts. Local media can remain the development default while the
settings shape prepares for S3-compatible storage.

## Reference Boundary

The older portal is a workflow reference, not the backend base.

Useful source concepts:

- Deterministic compliance timing from `computeDueNow.js` and
  `computeDueNow.server.js`
- Program schedules from `complianceRules.js`
- Buyer, program, submission, document, communication, template, note, and
  action queue shape from the Prisma schema
- Field mapping and value conversion knowledge from `filemakerFieldMap.js`
- Staff throughput patterns from the old compliance workstation

Non-goals:

- Do not move this repo into the old portal.
- Do not recreate the old portal's direct FileMaker integration.
- Do not add buyer-facing portal screens in this slice.
- Do not add email sending in this slice.

## FileMaker Rule

FileMaker is import and export compatibility only.

Allowed:

- Reading CSV exports.
- Writing CSV exports for manual re-import or reporting.
- Using the old field map as documentation for names, conversions, program
  mapping, and parcel normalization.

Not allowed:

- FileMaker Data API clients.
- FileMaker credentials.
- FileMaker sessions.
- Sync jobs.
- Push routes.
- Background tasks that call a GCLBA system.

## First Port

The first backend port is the deterministic compliance timing engine and the
action queue foundation.

The backend should own due-date and next-action calculation so dashboards,
exports, map layers, templates, and future queue endpoints all agree.

Initial service target:

`backend-django/tracker/services/compliance_timing.py`

Initial test target:

`backend-django/tracker/tests/test_compliance_timing.py`

## Initial Checklist

| ID | Task | Acceptance | Validation |
|---|---|---|---|
| CW-001 | Document unified backend direction | This file exists and names source of truth, storage direction, old portal role, and FileMaker boundary | Documentation review |
| CW-002 | Document field and model mapping | `FIELD_AND_MODEL_MAPPING.md` maps old portal concepts to future Django tables | Documentation review |
| CW-003 | Port timing engine | Python service computes program timing for the current `Property` shape and old portal flat records | Django unit tests |
| CW-004 | Cover four programs | Tests cover Featured Homes, Ready4Rehab, Demolition, and VIP | `python manage.py test tracker.tests.test_compliance_timing` |
| CW-005 | Preserve current frontend | No frontend changes in this slice | Git diff review |
| CW-006 | Write SOP replacement audit | `SOP_REPLACEMENT_AUDIT.md` classifies workflow areas as replaced, partial, missing, or redesign | Documentation review |
| CW-007 | Add workflow models | Normalized workflow tables exist beside `Property`, with additive migration coverage | `python manage.py test tracker.tests.test_workflow_models` |
| CW-008 | Seed default program rules and templates | Seed command is idempotent and updates existing program/template rows safely | `python manage.py test tracker.tests.test_workflow_models` |
| CW-009 | Add workflow queue and communication APIs | Workflow endpoints expose action queue, property timing, template preview, and communication logging without enabling email sending | `python manage.py test tracker.tests.test_workflow_api` |
| CW-010 | Wire the frontend action queue | A live `/workflow` route renders grouped queue sections from `/api/workflow/action-queue` | `npm run build` |
| CW-011 | Add mail-packet generation for missing-email cases | Staff can generate printable mail packet artifacts from queue or property detail | backend tests plus `npm run build` |
| CW-012 | Store generated proof and audit artifacts | Sent workflow communications and mail packets create durable `Document` rows under generated storage | `python manage.py test tracker.tests.test_workflow_api` |

## Future Model Direction

Add models beside the existing tracker models rather than rewriting the current
schema in one migration.

Candidate models:

- `Buyer`: contact, organization, status, buyer-level flags.
- `Program`: program key, label, cadence, schedule, grace days, uploads, docs.
- `ComplianceCase`: property-specific compliance state when the workflow grows
  beyond current rollup fields.
- `ActionItem`: generated or staff-created queue tasks.
- `EmailTemplate`: program and action-specific template variants.
- `TaxSnapshot`: tax state over time.
- `Document`: S3-backed files.
- `Note`: append-only internal activity history.

`Communication` already exists. It should evolve carefully rather than being
duplicated.

## Current Backend Workflow Surface

The additive workflow surface for this slice is now:

- `GET /api/workflow/action-queue`
- `GET /api/workflow/properties/{id}/timing`
- `GET /api/workflow/properties/{id}/template-preview`
- `GET /api/workflow/properties/{id}/communications`
- `POST /api/workflow/properties/{id}/communications`
- `GET /api/workflow/properties/{id}/documents`
- `POST /api/workflow/letters/packet`

The first frontend workflow surface is now:

- `/workflow` for grouped action-queue work
- `PropertyDetailPanel -> OutreachLog` for timing, template preview, packet generation, communication logging, and generated artifacts

Generated proof and packet files are stored under:

- `MEDIA_ROOT/generated_documents/...`
- Served through the existing `/images/*` path until a later object-storage cutover

This keeps email sending out of scope while giving the future frontend a
stable backend contract for queueing, preview, and communication logging.

## Production Gates

- Tests pass or failures are explained.
- No migration or data risk is introduced by the timing-service and workflow
  API slices.
- No secrets are added.
- No FileMaker live integration is added.
- The current import, review, imagery, detection, communication, and export
  behavior remains compatible.
- The rollback path is simple: remove the additive docs, workflow service, API
  routes, migration, and tests.
