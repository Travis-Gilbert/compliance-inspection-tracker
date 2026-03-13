# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Identity

**Name:** GCLBA Compliance Inspection Tracker
**Purpose:** Local desk-research triage tool for Genesee County Land Bank Authority compliance staff. Helps systematically review non-respondent properties using Google Street View, satellite imagery, and heuristic image detection before scheduling physical site visits.

**The governing constraint:** This tool is CSV-in, CSV-out. It never connects to FileMaker or any GCLBA system. It reads exported property lists, lets staff do desk research with imagery, and exports findings as CSV for manual re-import.

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async with aiosqlite
- **Frontend:** React 18 + Vite + Tailwind CSS (no TypeScript)
- **Database:** SQLite (single local file at `backend/data/compliance_tracker.db`)
- **External APIs:** Google Maps Platform (Street View Static, Maps Static, Geocoding)
- **Image Analysis:** NumPy + Pillow for heuristic vacancy/demolition detection

## Development Commands

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # Then add GOOGLE_MAPS_API_KEY
uvicorn app.main:app --reload     # http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
npm run build                     # Production build to dist/
```

### Both (typical dev session)
Start backend first (port 8000), then frontend (port 5173). Vite proxies `/api` and `/images` to the backend automatically via `vite.config.js`.

### API docs
FastAPI auto-generates Swagger UI at http://localhost:8000/docs when the backend is running.

### Useful Commands
```bash
# Stop orphaned backend server
lsof -ti:8000 | xargs kill

# Test pipeline via curl (after importing properties)
curl -s -X POST "http://127.0.0.1:8000/api/pipeline/process?limit=25" | python3 -m json.tool

# Test single geocode
curl -s -X POST "http://127.0.0.1:8000/api/imagery/geocode/{property_id}" | python3 -m json.tool
```

### Testing without Google API key
The tool functions for import, manual review, and export without a Google Maps API key. Geocoding, imagery fetching, and detection will return empty results but won't crash.

### Google Maps API gotcha
The API key must have three APIs enabled individually in Google Cloud Console: Geocoding API, Street View Static API, Maps Static API. If any are missing, the pipeline silently returns 0 processed (no error surfaced). Config loads via `load_dotenv()` at import time, so the server must be restarted after `.env` changes.

## Architecture

### Request flow
```
Browser (React, :5173)
  → Vite proxy (/api/*, /images/*)
    → FastAPI (:8000)
      → aiosqlite (SQLite)
      → Google Maps APIs (geocoding, imagery)
      → Disk cache (backend/data/images/)
```

### Backend layer structure

**`app/main.py`**: FastAPI app with lifespan (DB init), CORS config, router registration, and the pipeline endpoints (`/api/pipeline/process` and `/api/pipeline/process-stream`). The pipeline is defined here (not in a router) because it orchestrates across multiple services.

**`app/api/`** (route handlers):
- `properties.py` - All property CRUD, CSV import, stats, export. Prefix: `/api/properties`
- `imagery.py` - Geocoding and image fetching routes. Prefix: `/api/imagery`
- `detection.py` - Detection analysis routes. Prefix: `/api/detection`
- `comms.py` - Communication tracking (Phase 2 scaffolding). Prefix: `/api/communications`

**`app/services/`** (business logic, no HTTP concerns):
- `csv_parser.py` - Two-pass column auto-detection (exact match first, substring second)
- `geocoder.py` - Google Geocoding with Genesee County bounds bias
- `imagery.py` - Street View + satellite fetching with disk caching (MD5 filenames)
- `detector.py` - Heuristic image analysis (5 weighted signals, composite 0.0-1.0 score)
- `exporter.py` - CSV and text report generation

**`app/models/`** (data layer):
- `database.py` - SQLite connection via `get_db()` dependency, schema init
- `property.py` - Pydantic models (`PropertyCreate`, `PropertyUpdate`, `PropertyResponse`, `StatsResponse`), enums (`FindingType`, `DetectionLabel`, `Program`)
- `communication.py` - Phase 2 communication models

**`app/config.py`** - All settings from `.env`. Key values: `GOOGLE_MAPS_API_KEY`, `DATABASE_PATH`, `IMAGE_CACHE_DIR`, `VACANCY_THRESHOLD` (0.6), `DEMOLITION_THRESHOLD` (0.7).

### Database pattern

All async via aiosqlite. Route handlers get a connection via FastAPI dependency injection:
```python
async def some_route(db: aiosqlite.Connection = Depends(get_db)):
```
The pipeline endpoint in `main.py` opens its own connection directly (it runs long operations across multiple services).

Three tables: `properties` (main data, 25+ columns tracking the full lifecycle), `communications` (Phase 2), `import_batches` (tracking CSV imports).

### Frontend routing

| Path | Component | Purpose |
|------|-----------|---------|
| `/` | `Dashboard.jsx` | Stats, progress bar, pipeline controls |
| `/review` | `ReviewQueue.jsx` | Main work surface, property list sorted worst-first |
| `/property/:id` | `PropertyDetail.jsx` | Single property deep-dive with imagery |
| `/import` | `Import.jsx` | CSV file upload or text paste |
| `/export` | `Export.jsx` | Download options (full CSV, inspection list, summary) |

### Frontend API client

All backend calls go through `src/utils/api.js`. It exports named functions per endpoint (e.g., `getProperties()`, `updateProperty()`, `runPipeline()`). The Vite dev server proxy means the frontend uses relative paths (`/api/...`) with no base URL.

CSV import uses `FormData` (multipart), not JSON, because FastAPI requires `Form()` params when `UploadFile` is present.

### Pipeline (the core feature)

The pipeline endpoint (`POST /api/pipeline/process`) chains three steps in sequence:
1. **Geocode** ungeocoded properties (Google Geocoding API)
2. **Fetch imagery** for geocoded properties (Street View + satellite, cached to disk)
3. **Run detection** on properties with imagery (heuristic analysis, produces score + label)

There's also a streaming variant (`POST /api/pipeline/process-stream`) that emits Server-Sent Events for real-time progress in the Dashboard UI.

Both endpoints take `limit` (default 25) to batch-process. Users run the pipeline repeatedly until all properties are processed.

### Detection signals

Five heuristic signals weighted to produce a 0.0-1.0 composite score:
- **color_variance** (0.2): Low RGB std dev suggests boarded-up surfaces
- **green_coverage** (0.25): Upper-frame vegetation suggests overgrowth
- **edge_density** (0.3): Few edges = empty lot, many edges = structure present
- **brightness** (0.05): Weak signal for general condition
- **satellite_coverage** (0.2): Brown/bare ground vs. roof surfaces vs. canopy

Labels: `likely_occupied` (< 0.6), `likely_vacant` (>= 0.6, < 0.7), `likely_demolished` (>= 0.7).

## Domain Knowledge

### Programs and compliance expectations

| Program | What "Compliant" Means |
|---------|----------------------|
| Featured Homes | Property is occupied and maintained |
| Ready for Rehab | Renovation work reflects committed investment amount |
| VIP Spotlight | Per individual proposal terms |
| Demolition | Structure has been removed |

"Structure gone" is a problem for Featured Homes but expected for Demolition. Always cross-reference the program when evaluating findings.

### Finding values (from `constants.js` and `property.py`)

| Internal Value | Display Label | Meaning |
|---------------|---------------|---------|
| `visibly_renovated` | Visibly Renovated | Improvement work completed |
| `occupied_maintained` | Occupied & Maintained | Someone living there, property cared for |
| `partial_progress` | Partial Progress | Some work visible but incomplete |
| `appears_vacant` | Appears Vacant | No signs of occupancy or improvement |
| `structure_gone` | Structure Gone | Building removed |
| `inconclusive` | Needs Inspection | Can't determine from imagery, needs site visit |

All findings except `inconclusive` are considered "resolved" (desk-resolved, no site visit needed).

### Genesee County specifics

- Parcel ID format: `XX-XX-XXX-XXX` (e.g., `41-06-538-004`)
- Geocoding is bounds-biased to Genesee County (42.85,-83.95 to 43.20,-83.55)
- Addresses without a city get "Flint, MI" auto-appended
- Other recognized cities: Burton, Davison, Fenton, Flushing, Grand Blanc, Mt. Morris, Swartz Creek, Clio, Linden

## Hard Rules

1. **Never connect to FileMaker.** No Data API, no sessions, no field mapping. CSV-in, CSV-out only.
2. **Never deploy publicly.** No Vercel, no Railway. This runs locally.
3. **Never add user authentication.** Single-user local tool.
4. **Never use marketing language in the UI.** No "Powered by AI," no "Welcome to." Government tool, plain copy.
5. **Never overstate detection.** Labels are "likely" not "confirmed." Detection triages, humans assess.
6. **Never create buyer-facing interfaces.** This is internal staff tooling.
7. **Never add email sending.** Communication tracking logs events. It does not send messages.
8. **Never use em dashes** in text, copy, comments, or documentation. Use commas, semicolons, colons, or parentheses.
9. **Detection is triage, not assessment.** The human reviewer always makes the final call.

## Design tokens

Colors are defined in `frontend/tailwind.config.js` and `frontend/src/utils/constants.js`:
- Primary actions: civic green `#2E7D32`
- Secondary: civic blue `#1565C0`
- Page background: warm off-white `#FAFAF5`
- Typography: Bitter (headings), IBM Plex Sans (body), IBM Plex Mono (data)
- Status colors follow a traffic-light pattern per finding severity (green through red)

Aesthetic: civic utilitarian. High data density, no decoration. Think government desk tool, not SaaS dashboard.

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Backend (FastAPI + SQLite) | Done | All CRUD, import, export, stats, pipeline endpoints |
| Frontend (React + Vite) | Done | All 5 pages with routing, error boundaries, loading skeletons |
| CSV parser (smart column detection) | Done | Two-pass matching, BOM handling, \x0b stripping for FileMaker |
| Pipeline (geocode, imagery, detection) | Done | Tested end-to-end with 9 Flint properties; all three stages working |
| SSE streaming pipeline | Done | Real-time per-step progress bars in Dashboard |
| Keyboard shortcuts (PropertyDetail) | Done | Arrow keys prev/next, 1-6 for findings, Esc back to queue |
| Error boundaries + loading skeletons | Done | Per-route ErrorBoundary, page-specific skeletons |
| Communication tracking | Scaffolded | Backend API ready, no frontend integration yet |

### What's next

1. Import real non-respondent compliance CSV, tune detection thresholds on actual vacant/demolished properties
2. Communication tracking UI (Phase 2)
3. Dashboard trend charts (resolved per week)
4. Inspection route grouping (cluster properties geographically for efficient site visits)

## Sample test data

```csv
address,parcel_id,buyer_name,program,closing_date,commitment
307 Mason St,41-06-538-004,Derek Dohrman,Featured Homes,2024-03-15,$45000
1234 W Court St,41-11-234-012,Maria Santos,Ready for Rehab,2023-11-20,$80000
456 E Kearsley St,41-06-102-008,James Wilson,Featured Homes,2024-06-01,$35000
789 Saginaw St,41-06-441-015,Keisha Thompson,VIP Spotlight,2023-08-10,$120000
```

Fictional entries using real Flint street patterns and Genesee County parcel ID format.

## MCP Plugin

A Codex plugin exists at `../compliance-tracker-plugin/` that wraps the FastAPI backend as MCP tools. It provides:
- 9 MCP tools (search, get_property, update_finding, batch_update, get_stats, review_queue, import_csv, export_csv, run_pipeline)
- A compliance-review skill with institutional knowledge
- A read-only triage agent for batch recommendations
- Slash commands: `/tracker-review`, `/tracker-stats`, `/tracker-export`

The plugin proxies through the FastAPI backend (requires it to be running). See the plugin's own README for setup.

### Plugin deployment details
- **Installed at:** `~/.Codex/plugins/marketplaces/local-desktop-app-uploads/compliance-tracker/`
- **Registered in:** `~/.Codex/plugins/installed_plugins.json` as `compliance-tracker@local-desktop-app-uploads`
- **MCP server deps** (`fastmcp`, `httpx`, `pydantic`) must be installed in global Python, not the backend virtualenv: `pip3 install fastmcp httpx pydantic`
- **GitHub (private):** `Travis-Gilbert/compliance-inspection-tracker`
- **Plugin repo (private):** `Travis-Gilbert/compliance-tracker-plugin`
- After editing plugin files, copy changes to the install path: `cp -R ../compliance-tracker-plugin/ ~/.Codex/plugins/marketplaces/local-desktop-app-uploads/compliance-tracker/`
