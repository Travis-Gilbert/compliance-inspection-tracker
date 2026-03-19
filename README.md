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
├── frontend/                   # React application (Vite)
│   ├── src/
│   │   ├── App.jsx             # Root component + routing
│   │   ├── main.jsx            # React entry point
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx       # Stats overview + progress (Option 4 foundation)
│   │   │   ├── ReviewQueue.jsx     # Main work queue for desk research
│   │   │   ├── PropertyDetail.jsx  # Single property deep-dive with imagery
│   │   │   ├── Import.jsx          # CSV upload + preview + column mapping
│   │   │   └── Export.jsx          # Export options + report generation
│   │   ├── components/
│   │   │   ├── Layout.jsx          # App shell with nav sidebar
│   │   │   ├── PropertyCard.jsx    # Compact property row in queue
│   │   │   ├── ImageViewer.jsx     # Street View + satellite side-by-side
│   │   │   ├── FindingSelector.jsx # Finding buttons with color coding
│   │   │   ├── StatsBar.jsx        # Top-level progress stats
│   │   │   ├── FilterBar.jsx       # Filter tabs + search
│   │   │   └── ProgressRing.jsx    # Circular progress indicator
│   │   ├── hooks/
│   │   │   ├── useProperties.js    # Property data fetching + mutations
│   │   │   ├── useImagery.js       # Image loading + caching
│   │   │   └── useStats.js         # Computed statistics
│   │   └── utils/
│   │       ├── api.js              # Backend API client
│   │       └── constants.js        # Finding types, colors, programs
│   ├── index.html
│   ├── vite.config.js
│   ├── tailwind.config.js
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
```

Backend runs on http://localhost:8000
Frontend runs on http://localhost:5173

## Railway Deployment

This project can run as two Railway services:

- `backend`: FastAPI API
- `frontend`: static React app served from the included Docker image

### Backend service

Set the backend service to the `backend/` directory and provide:

- `GOOGLE_MAPS_API_KEY`
- your database connection env vars for Railway Postgres
- `CORS_ORIGINS=https://your-frontend-domain`

If you use multiple frontend domains, provide them as a comma-separated list.

### Frontend service

Set the frontend service to the `frontend/` directory and use the included `Dockerfile`.

Set this env var on the frontend service:

```bash
VITE_API_BASE_URL=https://your-backend-domain
```

The Docker image serves the built app with SPA fallback, so routes like
`/review`, `/property/123`, and `/map` load correctly.

### Monorepo setup

In Railway, create one service from `backend/` and one from `frontend/`.
Point the frontend service at the backend's public URL via `VITE_API_BASE_URL`.

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
