# Compliance Tracker v2: Unified Migration Task

See TASK-v2-unified.md for the complete Feature Handoff covering both
the Django Ninja backend conversion and Next.js frontend migration.

This file is a pointer. The full spec lives in the downloaded task file
and will be updated as the migration progresses.

## Quick Reference

- **Backend:** FastAPI + raw SQL -> Django Ninja + ORM + GeoDjango
- **Frontend:** Vite + React Router -> Next.js App Router + shadcn/ui
- **New fields:** compliance_status, tax_status, outreach tracking, homeowner_exemption
- **Structure:** Monorepo with backend-django/ + frontend-next/
- **Deploy:** Django on Railway, Next.js on Vercel
- **Services layer:** Copies verbatim (csv_parser, detector, geocoder, imagery, exporter, enrichment)
- **Only pipeline.py needs ORM conversion** (raw SQL queries become Django QuerySet calls)
