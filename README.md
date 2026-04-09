# GCLBA Compliance Inspection Tracker

A local inspection triage tool for the Genesee County Land Bank Authority. Helps compliance staff work through non-respondent properties systematically using desk research (Google Street View, satellite imagery) before scheduling physical site visits.

## What This Is

- A **personal productivity tool** for compliance inspection work
- Imports property lists from CSV exports (from FileMaker or Excel)
- Pulls Google Street View and satellite imagery for each address automatically
- Uses image analysis to flag likely-vacant or demolished properties for priority review
- Lets the reviewer record findings, add notes, and track progress
- Exports findings as CSV for re-import to FileMaker or reporting

## What This Is NOT

- Not connected to FileMaker (CSV in, CSV out)
- Not a replacement for the existing compliance portal or FileMaker workflows
- Not a public-facing tool (runs locally or on a private server)

## Architecture

```
compliance-tracker/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── main.py             # FastAPI app entry point, CORS, lifespan
│   │   ├── config.py           # Settings (API keys, DB path, image config)
│   │   ├── api/
│   │   │   ├── properties.py   # CRUD + CSV import/export routes
│   │   │   ├── imagery.py      # Google Maps image fetching routes
│   │   │   ├── detection.py    # Smart detection / image analysis routes
│   │   │   └── comms.py        # Communication tracking routes (Phase 2)
│   │   ├── services/
│   │   │   ├── csv_parser.py   # CSV import with column auto-detection
│   │   │   ├── geocoder.py     # Address to lat/lng conversion
│   │   │   ├── imagery.py      # Google Street View + Static Maps fetching
│   │   │   ├── detector.py     # Image analysis / vacancy detection
│   │   │   └── exporter.py     # CSV + report export generation
│   │   ├── models/
│   │   │   ├── database.py     # SQLite connection + table creation
│   │   │   ├── property.py     # Property model (Pydantic + DB schema)
│   │   │   └── communication.py # Communication log model (Phase 2)
│   │   └── utils/
│   │       ├── address.py      # Address normalization + parsing
│   │       └── images.py       # Image storage + thumbnail generation
│   ├── data/                   # SQLite DB + cached images (gitignored)
│   ├── requirements.txt        # Python dependencies
│   └── .env.example            # Environment variable template
│
├── frontend/                   # Next.js application (App Router)
│   ├── src/
│   │   ├── app/
│   │   │   ├── (main)/             # Dashboard, review, import, export, processing
│   │   │   └── map/                # Full-bleed management map
│   │   ├── components/
│   │   │   ├── LeadershipMap.tsx   # Full county map
│   │   │   ├── ManagementCoverageMap.tsx
│   │   │   └── review/             # Queue and detail components
│   │   ├── hooks/
│   │   │   ├── useReviewKeyboard.ts
│   │   │   └── useReviewQueue.ts
│   │   └── lib/
│   │       ├── api.ts              # Backend API client
│   │       └── constants.ts        # Finding types, colors, programs
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── package.json
│
└── README.md
```

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Google Maps Platform API key (Street View Static API + Geocoding API enabled)

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # Add your Google Maps API key
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
npm run build
```

Backend runs on http://localhost:8001 for the Django service
Frontend runs on http://localhost:3000

## Railway Deployment

This project can run as two Railway services:

- `backend`: Django Ninja API
- `frontend`: Next.js application deployed on Vercel

### Backend service

Set the backend service to the `backend-django/` directory and provide:

- `GOOGLE_MAPS_API_KEY`
- `DATABASE_URL` for Postgres, or `DATABASE_PATH` for SQLite
- `CORS_ORIGINS=https://your-frontend-domain`

If you use multiple frontend domains, provide them as a comma-separated list.
If `DATABASE_URL` is set, the backend uses Postgres automatically.

### Postgres migration

To copy a local SQLite tracker into Postgres:

```bash
cd backend
python3 scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path ./data/compliance_tracker.db \
  --database-url postgresql://...
```

This migrates properties, communications, and import batches. Cached imagery files stay on disk, so re-run imagery fetches or sync `IMAGE_CACHE_DIR` separately after the DB move.
By default, the migration script clears imagery and detection fields on the target because those cached files are not copied. Use `--preserve-derived-state` only if you are also moving the image cache.

### PostGIS note

The backend will attempt to enable PostGIS and add a spatial `location` column when the target database supports the extension. If the database host does not have the `postgis` package installed, startup continues without spatial columns.

### Frontend service

Deploy the frontend from the `frontend/` directory on Vercel.

Set this env var on the frontend deployment:

```bash
NEXT_PUBLIC_API_URL=https://your-backend-domain
```

If `NEXT_PUBLIC_API_URL` is omitted in production, the frontend falls back to the live Railway backend URL baked into `src/lib/api.ts`. Local development uses same-origin requests and `next.config.ts` rewrites to the backend.

### Monorepo setup

In Railway, create the backend service from `backend-django/`. In Vercel, point the frontend service at `frontend/` and set `NEXT_PUBLIC_API_URL` if you want to override the default production backend.

## Workflow

1. Export non-respondent properties from FileMaker as CSV
2. Import CSV into the tracker (auto-detects columns)
3. Tool geocodes addresses and fetches Street View + satellite imagery
4. Smart detection flags likely-vacant/demolished properties
5. Work through the review queue, recording findings for each property
6. Export findings as CSV for FileMaker re-import or reporting

## API Key

This tool requires a Google Maps Platform API key with the following APIs enabled:
- Street View Static API
- Maps Static API (for satellite imagery)
- Geocoding API

Google offers $200/month free credit, which covers roughly:
- 14,000 Street View Static API calls
- 100,000 Maps Static API calls
- 40,000 Geocoding API calls

For a batch of 300-500 properties, you'll stay well within free tier.

## Phase 2 (Future)

- Communication tracking (log outreach attempts, methods, responses)
- Compliance status rollup dashboard (Option 4)
- Batch outreach tools (email/text templates)
- Inspection scheduling and route optimization
- Before/after comparison views
