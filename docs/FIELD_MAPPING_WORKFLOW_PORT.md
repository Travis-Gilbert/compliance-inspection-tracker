# Field Mapping And Workflow Port

## Scope

This document maps the older portal concepts into the current Django workbench.
It is a planning document for normalized workflow tables and timing logic. It
does not authorize a FileMaker connection.

The live base is `backend-django/tracker/models.py`.
The reference base is the older portal's Prisma schema, compliance rules, and
field map.

## Current Django Anchor

`Property` is the anchor model. It already stores:

| Area | Current fields |
|---|---|
| Identity | `address`, `address_key`, `parcel_id` |
| Buyer rollup | `buyer_name`, `email`, `organization` |
| Sale/program | `program`, `closing_date`, `commitment`, `purchase_type` |
| Legacy outreach | `compliance_1st_attempt`, `compliance_2nd_attempt` |
| Spatial/imagery | `latitude`, `longitude`, `formatted_address`, image paths, fetch timestamps |
| Detection | `detection_score`, `detection_label`, `detection_details`, `detection_ran_at` |
| Staff review | `finding`, `notes`, `reviewed_at`, `reviewed_by` |
| Compliance rollup | `compliance_status`, outreach counts, last outreach fields |
| Tax rollup | `tax_status`, `last_tax_payment`, `tax_amount_owed`, `homeowner_exemption` |
| Cross-reference | `regrid_condition`, `portal_survey_date`, `import_batch` |

These fields should remain as current-state rollups while normalized workflow
models are added around them.

## Program Mapping

| Source value | Canonical key | Display label | Current Django value examples |
|---|---|---|---|
| `FeaturedHomes`, `Featured`, `FH adj VL` | `FeaturedHomes` | Featured Homes | `Featured Homes` |
| `Ready4Rehab`, `R4R`, `R4R adj VL` | `Ready4Rehab` | Ready4Rehab | `Ready for Rehab`, `Ready4Rehab` |
| `Demolition`, `Demo` | `Demolition` | Demolition | `Demolition` |
| `VIP` | `VIP` | VIP | `VIP`, `VIP Spotlight` |

The timing service should accept current display labels and old portal keys.
Later, the `Program` model should store the canonical key and label.

## Old Portal To Django Model Direction

| Old portal concept | Current Django location | Future Django direction | Notes |
|---|---|---|---|
| `Buyer` | `Property.buyer_name`, `email`, `organization` | New nullable `Buyer` model | Preserve rollups for CSV compatibility |
| `Program` | `Property.program` | New `Program` model | Stores cadence, schedule, grace days, required uploads, required docs |
| `Property` | `Property` | Keep current model | Add relationships gradually |
| `Communication` | `Communication` | Evolve existing table | Add action, template, status, recipient, provider ID, approval timestamp, body hash |
| `EmailTemplate` | None | New `EmailTemplate` model | Preview first, no sending |
| `Submission` | None | Defer | Needed when buyer upload workflow exists |
| `Document` | `PropertyPhoto` direction, image paths | New `Document` model | S3-compatible storage target |
| `Note` | `Property.notes` | New append-only `Note` model | Keep `notes` as rollup or export field |
| `TaxSnapshot` | Current tax rollup fields | New `TaxSnapshot` model | Preserve historical tax checks |
| `OutreachTask` or `ActionItem` | Priority queue logic | New `ActionItem` model | Generated queue tasks can start as API-only before persistence |

## Compliance Timing Field Mapping

| Timing input | Current Django field | Old portal field | Handling |
|---|---|---|---|
| Program | `program` | `programType` | Normalize to canonical program key |
| Close date | `closing_date` | `closeDate`, `dateSold` | Parse flexible CSV and ISO dates |
| First attempt sent | `compliance_1st_attempt` | `compliance1stAttempt` | Any non-empty value completes `ATTEMPT_1` |
| Second attempt sent | `compliance_2nd_attempt` | `compliance2ndAttempt` | Any non-empty value completes `ATTEMPT_2` |
| Communication action | Future `Communication.action` | `communications[].action` | Count sent actions as completed |
| Communication status | Future `Communication.status` | `communications[].status` | Treat sent or dated communications as completed when an action is present |
| Last contact | `last_outreach_date`, `Communication.date_sent` | `lastContactDate` | Use direct field first, otherwise latest communication date |

## Default Program Rules

The first timing slice ports the deterministic default rules:

| Program | Cadence | Grace days | Schedule |
|---|---|---:|---|
| Featured Homes | monthly | 3 | 30 `ATTEMPT_1`, 60 `ATTEMPT_2`, 90 `WARNING`, 120 `DEFAULT_NOTICE` |
| Ready4Rehab | monthly | 3 | 30 `ATTEMPT_1`, 60 `ATTEMPT_2`, 90 `WARNING`, 120 `DEFAULT_NOTICE` |
| Demolition | milestones | 0 | 14 `ATTEMPT_1`, 30 `WARNING`, 45 `DEFAULT_NOTICE` |
| VIP | quarterly | 5 | 90 `ATTEMPT_1`, 120 `ATTEMPT_2`, 150 `WARNING`, 180 `DEFAULT_NOTICE` |

The future `seed_workflow_defaults` command should create these as database
rows and keep the Python defaults as a fallback.

## FileMaker Compatibility Notes

`filemakerFieldMap.js` remains useful because it names:

- Parcel ID and address fields.
- Program mapping from Sales Disposition values.
- Buyer portal fields such as name, organization, co-applicant, interest type,
  date received, closing, email, and phone.
- Date, boolean, number, and currency conversion behavior.
- Confirmed fields versus unknown fields.

This knowledge should inform CSV import and export compatibility. It should not
be used to create a live FileMaker client.

## Migration Path

1. Add the Python compliance timing service using current `Property` fields.
2. Add `Program` and `Buyer` as nullable relationships while preserving current
   rollup fields.
3. Add `EmailTemplate`, `ActionItem`, `TaxSnapshot`, `Document`, and `Note`.
4. Evolve `Communication` in place.
5. Add seed command for default programs and draft templates.
6. Add action queue endpoints that explain every priority reason.
7. Add frontend queue and template preview surfaces.

## Implementation Notes

The first model slice added `Buyer`, `Program`, `ActionItem`, `EmailTemplate`,
`TaxSnapshot`, `Document`, and `Note` as concrete Django models. It also added
nullable `buyer` and `program_record` links to `Property`, while preserving
`buyer_name`, `email`, `organization`, and `program` as current-state rollups.

`Communication` was extended in place with optional workflow fields for action,
template, status, recipient, provider message ID, approval timestamp, send
timestamp, and body hash. Existing rows default to `logged`, so old
communication history is not reclassified as sent email.

The `seed_workflow_defaults` command creates or updates the four default
program rules and three draft email templates. Templates are seeded as inactive
drafts so this remains preview and logging infrastructure, not email sending.

## Deferrals

| Item | Why deferred |
|---|---|
| Direct FileMaker calls | Not allowed by project boundary |
| Email sending | Preview and logging must come first |
| Buyer portal tokens | Internal staff workbench comes first |
| Full S3 migration | Settings and model direction come before production storage cutover |
| Full frontend redesign | Backend workflow spine must be stable first |
