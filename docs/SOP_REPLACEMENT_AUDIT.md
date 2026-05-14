# SOP Replacement Audit

## Scope

This audit compares three surfaces:

- The manual SOP described in `Compliance update.md`
- The older portal reference at `../Compliance.Thelandbank.org- Feb - 12/`
- The live Django and Next.js workbench in this repository

The goal is to mark each workflow area as:

- `replaced`
- `partially replaced`
- `not replaced`
- `should be redesigned`

The hard boundary remains unchanged: CSV in, CSV out; no direct FileMaker
connection.

## Summary

| Area | Old portal evidence | Current workbench evidence | Status | Notes |
|---|---|---|---|---|
| Data import and report extraction | `src/config/filemakerFieldMap.js`, FileMaker-shaped property fields in `prisma/schema.prisma` | CSV import pipeline in `backend-django/tracker/services/csv_parser.py`, import routes in `backend-django/tracker/api.py` | `replaced` | The new repo already handles CSV intake without reviving FileMaker sync. |
| Sorting and grouping | `src/pages/ActionQueue.jsx` grouped due items by workflow action | `GET /api/workflow/action-queue`, frontend `/workflow` route | `replaced` | Grouped queue work now exists in both the backend and the live Next.js app. |
| First and second attempt separation | `src/lib/computeDueNow.js` plus `compliance1stAttempt` and `compliance2ndAttempt` in `prisma/schema.prisma` | `backend-django/tracker/services/compliance_timing.py`, `Property.compliance_1st_attempt`, `Property.compliance_2nd_attempt` | `replaced` | Deterministic timing and attempt separation now live in Python and are test-covered. |
| Email validation and missing-email isolation | `ActionQueue.jsx` split records with `buyerEmail` from no-email records | `GET /api/workflow/action-queue`, frontend `/workflow` route, packet generation controls | `replaced` | Missing-email cases are now isolated in the queue and routed into packet generation. |
| Template selection | `src/lib/templateRenderer.js`, `src/pages/TemplateManager.jsx` | `EmailTemplate` model, `seed_workflow_defaults`, `GET /api/workflow/properties/{id}/template-preview` | `partially replaced` | Preview routing is backend-owned now, but full template management UI still belongs to a later slice. |
| Email preview | `src/components/EmailPreview.jsx` and `templateRenderer.js` | `GET /api/workflow/properties/{id}/template-preview` | `replaced` | The preview contract now exists on the backend and can drive a future UI. |
| Email sending | `src/lib/emailSender.js` used Resend with mock fallback | No sending route in this repo by design | `should be redesigned` | This project explicitly stops at preview and logging until approval rules are settled. |
| Snail-mail handling | `ActionQueue.jsx` surfaced no-email records and mail-merge paths | Missing-email queue items, `POST /api/workflow/letters/packet`, generated packet documents | `partially replaced` | Printable packet generation now exists, but mailing-address verification and actual send confirmation remain manual. |
| Proof of investment and required uploads | `complianceRules.js` listed required uploads and docs per program | `Program.required_uploads`, `Program.required_docs`, seeded defaults | `partially replaced` | The data model is ready, but buyer submission and review workflow are still deferred. |
| Demolition final certification | `demoFinalCertDate` in `prisma/schema.prisma` | Demolition timing rules are ported; no dedicated final-cert workflow yet | `not replaced` | This remains a later document and submission workflow slice. |
| VIP recurring compliance | `VIP` rules in `complianceRules.js`, `complianceType` in Prisma | VIP schedule and grace period are ported in `compliance_timing.py` and seeds | `partially replaced` | The default cadence exists, but per-agreement VIP customization is still a gap. |
| PDF and document filing | `Document` model in Prisma, email logging assumptions in the old portal | `Document` model, generated communication proof files, generated mail packet files | `partially replaced` | Durable generated artifacts are now stored, but there is still no true PDF renderer or final filing workflow. |
| FileMaker field updates | Old portal assumed writeback pathways and FileMaker-compatible field maps | CSV export remains the only supported outbound path | `should be redesigned` | The workbench should export compatible CSVs, not push live updates. |
| Communication audit trail | `PropertyContext.jsx` logged outbound messages into local state | `Communication` model, legacy `/api/communications`, new workflow logging route | `replaced` | Durable backend communication logging now exists and updates property rollups when a message is marked sent. |
| Property-level notes | `Note` model in Prisma and local UI note patterns | `Property.notes` plus additive `Note` model in Django | `partially replaced` | Backend storage exists, but the newer append-only note UI is still deferred. |
| Map and inspection workflow | Old portal was lighter on spatial operations | Review queue, property detail, map routes, photo evidence, and detection pipeline in this repo | `replaced` | The new tracker is clearly stronger here and should remain the foundation. |
| Dashboard and observability | Old portal offered action counts and workflow reporting pages | Dashboard, stats endpoints, pipeline SSE, and map summaries already exist | `partially replaced` | The operational base is here; the dedicated compliance observability layer still needs workflow-specific charts. |
| Persistence and source of truth | Prisma schema was strong, but frontend local state and mock-data fallbacks blurred authority | Django ORM + Postgres/PostGIS is the source of truth | `replaced` | This is the biggest structural improvement over the older portal. |

## Findings

### Replaced well

- Deterministic timing is now backend-owned instead of frontend-owned.
- The canonical storage direction is clearer: Django/PostGIS for state, object
  storage later for files.
- Spatial review, imagery, and inspection triage are stronger in this repo
  than they ever were in the portal.
- Communication logging now has a durable backend path instead of reducer-only
  state.

### Partially replaced

- Template preview is now an API contract, but template editing, approval, and
  broader batch operations remain future work.
- Workflow models and seeded defaults exist, and generated artifacts now land,
  but property-level audit browsing is still lightweight.

### Not replaced or redesign required

- Sending email directly from this system is intentionally out of scope for
  now.
- PDF filing, letter packet generation, and demolition final-cert handling are
  still open implementation lanes.
- FileMaker live sync should stay retired; CSV compatibility is the correct
  replacement strategy.

## Recommended Sequence

1. Wire the new workflow API routes into a backend-backed action queue UI.
2. Add printable letter and mail-packet generation for `MISSING_EMAIL` cases.
3. Add document generation and filing for sent communications and proof
   artifacts.
4. Add append-only notes and audit views to make communication and review
   history visible in one place.
