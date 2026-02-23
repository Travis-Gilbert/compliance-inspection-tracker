# CLAUDE.md - Compliance Inspection Tracker

## Project Identity

**Name:** GCLBA Compliance Inspection Tracker
**Owner:** Travis Gilbert, Project Manager, Genesee County Land Bank Authority
**Purpose:** A local desk-research triage tool that helps compliance staff systematically work through non-respondent properties using Google Street View imagery, satellite photos, and smart image detection before scheduling physical site visits.

This tool exists because the Land Bank sells hundreds of properties per year through programs that require buyers to make improvements. After closing, the Land Bank needs to verify buyers followed through. Email outreach gets roughly a one-third response rate. The other two-thirds go silent. This tool addresses that two-thirds by enabling efficient desk research and image-based triage so the reviewer can resolve as many properties as possible without leaving the office, and prioritize the remainder for physical inspection.

---

## Organizational Context (Critical - Read Before Making Decisions)

This project was born from a specific conversation with Christina Kelly, Director of Community Impact at GCLBA. Her feedback directly shapes what this tool is and is not.

### What Christina Asked For
1. A way to systematically work through non-respondent properties
2. Digital desk research before field visits (Google Street View, Flint Property Portal, satellite imagery)
3. Shrinking the pool of unknowns: start with the full list, resolve what you can digitally, flag the rest for inspection
4. Tracking progress with clear numbers (how many total, how many reviewed, how many resolved, how many need visits)
5. Eventually: physical inspection tracking and communication/outreach logging

### What Christina Explicitly Does NOT Want
1. Any connection to the FileMaker database (no API calls, no Data API, no read or write access)
2. A portal that duplicates the one being built by the FileMaker consultant
3. A buyer-facing submission tool (that's the other portal's job)
4. Anything that requires IT security review or creates a new database endpoint
5. Scope creep into systems that need organizational approval

### The Guardrail That Governs Everything
**This tool is CSV-in, CSV-out.** It reads property lists exported from FileMaker. It writes findings to CSV files that can be handed to whoever does FileMaker data entry. It never touches FileMaker directly. It never creates a network connection to any GCLBA system. It runs locally or on a private server. If anyone asks what this is, the answer is: "It's a tool that helps me work through property inspections faster using Street View images. I export a list, it pulls up the properties, I record what I see, and I export my findings. It doesn't touch FileMaker."

---

## Technical Architecture

### Stack
- **Backend:** FastAPI (Python 3.10+), async, with aiosqlite for local storage
- **Frontend:** React 18 + Vite + Tailwind CSS
- **Database:** SQLite (local file, no external database)
- **External APIs:** Google Maps Platform (Street View Static API, Maps Static API, Geocoding API)
- **Image Analysis:** NumPy + Pillow for heuristic-based vacancy/demolition detection

### Why FastAPI Over Django
This tool's core workload is I/O-bound: fetching hundreds of Street View images from Google's API concurrently. FastAPI's native async support with httpx makes this fast. Django's synchronous default would require Celery or Channels for the same result. FastAPI is also lighter for a single-user tool with a simple data model. If this later becomes a multi-user organizational tool, migration to Django is straightforward since the business logic is framework-agnostic.

### Project Structure
```
compliance-tracker/
├── CLAUDE.md                       # This file
├── README.md                       # Setup instructions + user documentation
├── backend/
│   ├── .env.example                # Environment variable template
│   ├── requirements.txt            # Python dependencies
│   ├── app/
│   │   ├── main.py                 # FastAPI entry + CORS + pipeline endpoint
│   │   ├── config.py               # Settings from .env
│   │   ├── api/
│   │   │   ├── properties.py       # CRUD, CSV import/export, stats, filters
│   │   │   ├── imagery.py          # Geocoding + Street View/satellite fetching
│   │   │   ├── detection.py        # Smart image analysis routes
│   │   │   └── comms.py            # Communication tracking (Phase 2)
│   │   ├── services/
│   │   │   ├── csv_parser.py       # CSV import with column auto-detection
│   │   │   ├── geocoder.py         # Google Geocoding API client
│   │   │   ├── imagery.py          # Street View + satellite image fetching
│   │   │   ├── detector.py         # Heuristic image analysis engine
│   │   │   └── exporter.py         # CSV + text report generation
│   │   ├── models/
│   │   │   ├── database.py         # SQLite schema + init
│   │   │   ├── property.py         # Pydantic models + enums
│   │   │   └── communication.py    # Communication log models
│   │   └── utils/
│   │       ├── address.py          # Address normalization for Flint/Genesee Co
│   │       └── images.py           # Image caching + thumbnails
│   └── data/                       # SQLite DB + cached images (gitignored)
│
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js              # Proxy /api to FastAPI backend
    ├── tailwind.config.js          # GCLBA civic design tokens
    ├── postcss.config.js
    └── src/
        ├── main.jsx                # React entry
        ├── index.css               # Tailwind directives
        ├── App.jsx                 # Routing
        ├── components/
        │   └── Layout.jsx          # Sidebar nav shell
        ├── pages/
        │   ├── Dashboard.jsx       # Stats + pipeline controls
        │   ├── ReviewQueue.jsx     # Main work queue
        │   ├── PropertyDetail.jsx  # Single property deep-dive
        │   ├── Import.jsx          # CSV upload
        │   └── Export.jsx          # Download options
        └── utils/
            ├── api.js              # Backend API client
            └── constants.js        # Findings, detection labels, colors
```

---

## The Core Workflow (User Journey)

### Step 1: Import
User exports a CSV of non-respondent properties from FileMaker. The CSV contains at minimum: address. Optionally: parcel ID, buyer name, program type, closing date, committed investment amount. The tool auto-detects columns regardless of header names or order. User uploads via the Import page.

### Step 2: Process (Pipeline)
User clicks "Run Pipeline" on the Dashboard. This triggers three sequential operations:
1. **Geocode:** Convert each address to lat/lng via Google Geocoding API (biased toward Genesee County)
2. **Fetch Imagery:** Pull Street View and satellite images for each geocoded property, cache locally
3. **Smart Detection:** Run heuristic image analysis on each property, produce a score (0.0 to 1.0) and label (likely_occupied, likely_vacant, likely_demolished)

The pipeline processes in batches (default 25) with rate limiting to respect Google API quotas. User can run it multiple times until all properties are processed.

### Step 3: Review
Properties appear in the Review Queue, sorted worst-first by detection score. For each property, the reviewer:
- Sees the Street View image thumbnail in the queue list
- Clicks into the Property Detail page
- Views Street View and satellite imagery side by side
- Opens interactive Street View, Flint Property Portal, or Google Maps via one-click links
- Records a finding: Visibly Renovated, Occupied & Maintained, Partial Progress, Appears Vacant, Structure Gone, or Inconclusive/Needs Inspection
- Adds notes (e.g., "Street View dated June 2025 shows new siding and windows")
- Moves to the next property

### Step 4: Export
User downloads findings as:
- **Full CSV:** All properties with findings, detection results, notes (for FileMaker re-import)
- **Inspection List:** Only properties needing site visits (formatted for field use)
- **Summary Report:** Plain text with progress stats and breakdowns (for leadership updates)

### Step 5: Report (Option 4 - Dashboard)
The Dashboard shows real-time stats: total properties, reviewed count, resolved without visit, flagged for inspection, progress percentage, breakdowns by finding type, by program, and by detection result. This is the foundation for the compliance status rollup Christina described wanting.

---

## Feature Specifications

### F1: CSV Import with Smart Column Detection
**File:** `backend/app/services/csv_parser.py`

The parser must handle messy real-world data from FileMaker exports:
- Auto-detect delimiter (comma, tab, pipe)
- Auto-detect header row vs. headerless data
- Match column names flexibly (e.g., "Buyer Name", "buyer_name", "BUYER", "purchaser", "owner" all map to buyer_name)
- Detect parcel IDs by regex pattern: `\d{2}-\d{2}-\d{3}-\d{3}` (Genesee County format)
- Handle quoted fields, UTF-8 BOM, and Windows line endings
- Skip blank rows gracefully
- Report errors per row without failing the entire import
- Assign a batch_id to each import for tracking

Column detection patterns (from most to least specific):
- **address:** "address", "street", "location", "property_address", "street_address"
- **parcel_id:** "parcel", "parcel_id", "pin", "apn", "tax_id", "parcel_number"
- **buyer_name:** "buyer", "name", "owner", "purchaser", "full_name", "contact"
- **program:** "program", "type", "program_type", "sale_type", "category"
- **closing_date:** "closing", "close_date", "sale_date", "sold", "date_sold"
- **commitment:** "commitment", "invest", "investment", "amount", "cost", "budget", "rehab_cost"

### F2: Geocoding
**File:** `backend/app/services/geocoder.py`

- Use Google Geocoding API with bounds bias toward Genesee County (42.85,-83.95 to 43.20,-83.55)
- Auto-append "Flint, MI" to addresses that don't already include a city
- Recognize other Genesee County cities: Burton, Davison, Fenton, Flushing, Grand Blanc, Mt. Morris, Swartz Creek, Clio, Linden
- Batch process with concurrency limit of 10 simultaneous requests
- 200ms delay between batches to respect rate limits
- Store: latitude, longitude, formatted_address, geocoded_at timestamp

### F3: Imagery Fetching
**File:** `backend/app/services/imagery.py`

For each geocoded property, fetch two images:

**Street View:**
- Check metadata endpoint first to verify availability and get image date
- Fetch outdoor-source images at 640x480
- Cache to disk using MD5 hash of address as filename
- Store: file path, availability flag, image date string
- Skip re-fetch if cached image exists

**Satellite:**
- Use Maps Static API with maptype=satellite, zoom=19
- Same caching strategy
- 640x480 resolution

Batch processing: 5 concurrent fetches, 300ms between batches.

### F4: Smart Detection (Image Analysis)
**File:** `backend/app/services/detector.py`

This is the feature that reduces workload by auto-sorting the worst properties to the top. It runs heuristic computer vision on cached images to produce a condition score.

**Street View Analysis (when available):**
1. **Color Variance** (weight 0.2): Low variance suggests boarded-up windows or uniform vacant surfaces. Measure std dev across RGB channels. Normal houses: std > 55. Suspicious: std < 20.
2. **Green Coverage** (weight 0.25): Heavy vegetation, especially in the upper frame where a structure should be, suggests overgrowth/vacancy. Detect green-dominant pixels (G > R+15 and G > B+15). Upper-frame green > 50% is a strong vacancy signal.
3. **Edge Density** (weight 0.3): Structures have many edges (windows, doors, rooflines). Empty lots have few. Use simple Sobel-like gradient detection. Count strong edges (gradient > 30). Normal buildings: edge ratio > 0.08. Empty lots: < 0.02.
4. **Brightness** (weight 0.05): Mild signal. Very dark or washed-out images correlate weakly with poor condition.

**Satellite Analysis (when available):**
5. **Satellite Coverage** (weight 0.2): Detect brown/bare ground (possible demolition), dense canopy (overgrowth), and gray/roof surfaces (structure present). High brown + low gray = likely demolished. Very high canopy = likely abandoned.

**Scoring:**
- Composite score 0.0 (likely fine) to 1.0 (likely problem)
- Labels: "likely_occupied" (< vacancy threshold), "likely_vacant" (>= vacancy threshold), "likely_demolished" (>= demolition threshold)
- Default thresholds: vacancy = 0.6, demolition = 0.7 (configurable via .env)
- Store: score, label, full details JSON (all signal values and weights), detection_ran_at timestamp

**Important:** This is triage, not assessment. The detection sorts properties so the reviewer looks at the worst ones first. It will produce false positives and false negatives. The human reviewer makes the actual finding. Never present detection results as definitive to users or stakeholders.

**Future improvement:** Replace heuristics with a trained CNN model (e.g., fine-tuned ResNet on blight detection datasets from Detroit/Flint research). The service interface is designed so swapping the analysis engine requires changing only the detection functions, not the API layer.

### F5: Review Queue
**File:** `frontend/src/pages/ReviewQueue.jsx`

The primary work surface. Must be efficient for processing dozens of properties in a session.

- **Default sort:** Detection score descending (worst first). This is the key UX decision: the smart detection determines what the reviewer sees first.
- **Alternate sorts:** Newest import first, address alphabetical, recently reviewed
- **Filters:** All, Unreviewed, Resolved (desk), Needs Inspection
- **Search:** Real-time filter by address, parcel ID, buyer name
- **Each property row shows:** Street View thumbnail (small, 80x56px), address, parcel ID, buyer name, program badge, detection label badge, finding badge (if reviewed)
- **Click to open:** Property Detail page

Keyboard navigation (implement in Phase 2): arrow keys to move between properties, enter to open, number keys 1-6 to assign findings from the detail page.

### F6: Property Detail Page
**File:** `frontend/src/pages/PropertyDetail.jsx`

The deep-dive view for a single property. Layout:

1. **Header:** Address (large), parcel ID, buyer name, program badge, closing date, committed investment
2. **Detection alert:** If detection ran, show label and score in a colored banner
3. **Imagery grid:** Street View (left) and satellite (right), side by side on desktop, stacked on mobile. Street View image date shown if available.
4. **Research links:** Three buttons opening in new tabs:
   - "Open Street View (Interactive)" - Google Maps panorama at the property coordinates
   - "Flint Property Portal" - search by address on flintpropertyportal.com
   - "Google Maps" - standard maps view
5. **Finding selector:** Six buttons, color-coded, toggle behavior (click to set, click same to clear). When set, auto-populates reviewed_at timestamp.
6. **Notes textarea:** Free-form, auto-save on blur or explicit save button. Placeholder suggests what to write: "Street View shows recent renovation work. New siding visible. Image dated June 2025."
7. **Metadata footer:** Reviewed timestamp, geocode timestamp, formatted address, lat/lng

### F7: Dashboard (Option 4 Foundation)
**File:** `frontend/src/pages/Dashboard.jsx`

The numbers view Christina described wanting. Shows:

- **Progress bar:** Percentage of properties reviewed, with reviewed/remaining counts
- **Stat cards:** Total, Resolved (desk), Needs Inspection, Unreviewed
- **Pipeline controls:** "Run Pipeline" button that processes the next batch. Shows Google Maps API status (configured/not configured). Displays pipeline results after each run.
- **Detection breakdown:** How many properties in each detection category
- **Findings breakdown:** How many properties with each finding type
- **Program breakdown:** Properties by program (Featured Homes, Ready for Rehab, etc.)

Phase 2 additions: trend over time (properties resolved per week), communication response rates, inspection completion tracking.

### F8: Export
**File:** `frontend/src/pages/Export.jsx`, `backend/app/services/exporter.py`

Four export options:
1. **Full CSV:** All properties with all fields. Headers match FileMaker-friendly naming.
2. **Inspection List:** Only properties needing site visits. Includes blank columns for on-site findings and date (to be filled in the field, printed or used on a tablet).
3. **Summary Report:** Plain text formatted for email. Includes date, total counts, progress percentage, desk resolution rate, findings breakdown, program breakdown. This is what Travis sends to Christina.
4. **Resolved Properties:** Only desk-resolved properties. For updating FileMaker compliance status.

### F9: Communication Tracking (Phase 2)
**File:** `backend/app/api/comms.py`, `backend/app/models/communication.py`

Log outreach attempts per property:
- Method: email, mail, phone, text, site_visit
- Direction: outbound (we contacted them) or inbound (they contacted us)
- Date, subject, body
- Response tracking: received yes/no, response date, response notes
- Stats: response rate by method, total outreach attempts

This is scaffolded but not fully built into the frontend yet. Build it when Travis has worked through the initial review queue and needs to start the outreach phase.

---

## Design System

### Aesthetic Direction
Civic utilitarian. This is a government operations tool, not a marketing site. Clean, efficient, high data density. No decorative elements. No animations except subtle transitions on interactive elements. Think well-organized desk, not SaaS dashboard.

### Colors
```
Civic green:        #2E7D32  (primary actions, positive status)
Civic green light:  #4CAF50  (hover states)
Civic green pale:   #E8F5E9  (active nav, positive backgrounds)
Civic blue:         #1565C0  (program badges, secondary actions)
Civic blue pale:    #E3F2FD  (info backgrounds)

Warm surfaces:
  50:  #FAFAF5   (page background)
  100: #F5F5F0   (alternate background)
  200: #E8E8E0   (borders, dividers)

Status colors (findings):
  Renovated:    #2E7D32 / #E8F5E9
  Occupied:     #1565C0 / #E3F2FD
  Partial:      #F57F17 / #FFF8E1
  Vacant:       #E65100 / #FFF3E0
  Demolished:   #B71C1C / #FFEBEE
  Inconclusive: #4A148C / #F3E5F5

Detection colors:
  Likely occupied:   #2E7D32 / #E8F5E9
  Likely vacant:     #E65100 / #FFF3E0
  Likely demolished: #B71C1C / #FFEBEE
```

### Typography
- **Headings:** Bitter (serif), weights 400/600/700
- **Body:** IBM Plex Sans, weights 400/500/600
- **Monospace:** IBM Plex Mono (code snippets, CSV previews, technical data)
- Load from Google Fonts CDN

### Component Patterns
- **Cards:** White background, 1px #E0E0E0 border, 8px border-radius, colored left border (3px) for status indication
- **Buttons:** Rounded-md (5px), font-medium, transition-colors. Primary: civic green bg, white text. Secondary: gray bg. Danger: red text, no bg.
- **Badges:** Small rounded pills with colored text on pale background. Used for program types, finding labels, detection labels.
- **Form inputs:** 1px #E0E0E0 border, 5px radius, IBM Plex Sans 13px. Focus: civic green border.
- **Filter tabs:** Small buttons, active state uses civic green pale background with green text.
- **Stat cards:** White card with colored left border (3px), uppercase label (11px), large number (Bitter 28px), optional sublabel.

### Responsive Behavior
- Sidebar: full-width horizontal on mobile, 224px vertical sidebar on desktop (md breakpoint)
- Image grid: stacked on mobile, 2-column on desktop
- Stat cards: 2-column on mobile, 4-column on desktop
- Property rows: full width, thumbnail hidden on very small screens if needed

---

## Development Commands

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # Add GOOGLE_MAPS_API_KEY
uvicorn app.main:app --reload     # Starts on http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                       # Starts on http://localhost:5173
```

### API Documentation
FastAPI auto-generates interactive docs at http://localhost:8000/docs (Swagger UI).

### Testing the Pipeline Without Google API Key
The tool works without a Google Maps API key for import, review, and export. Geocoding, imagery, and detection will return empty results, but the rest of the workflow functions. Set `GOOGLE_MAPS_API_KEY` in `.env` when ready to enable imagery.

---

## Implementation Priorities

### Priority 1: Make the Core Loop Work
1. Verify CSV import handles real FileMaker exports (test with various column layouts)
2. Verify the pipeline endpoint chains geocode -> imagery -> detection correctly
3. Verify the Review Queue loads, sorts by detection score, and navigates to Property Detail
4. Verify Property Detail displays images from cache, allows finding selection, saves notes
5. Verify Export generates valid CSVs

### Priority 2: Polish the Frontend
1. Make the Review Queue feel fast and efficient for processing 20+ properties in a session
2. Add loading states, error handling, and empty states throughout
3. Ensure mobile responsiveness (Travis will use this on a laptop but may demo on a phone)
4. Add "next property" / "previous property" navigation on the Property Detail page so the reviewer can move through the queue without going back to the list
5. Show a progress indicator during pipeline runs (not just a spinning state, but "Geocoding 15/25... Fetching imagery 8/25... Running detection 3/25...")

### Priority 3: Improve Detection Accuracy
1. Test heuristic detection against known properties (Travis can provide addresses of properties he knows are vacant vs. renovated)
2. Tune thresholds based on real results
3. Add more signals if the current ones produce too many false positives
4. Consider adding a "detection confidence" display so the reviewer knows how much to trust the score

### Priority 4: Communication Tracking (Phase 2)
1. Add a communications panel to the Property Detail page
2. Log outreach attempts with method, date, notes
3. Track responses
4. Add communication count to the Review Queue property rows
5. Add response rate stats to the Dashboard

### Priority 5: Dashboard Expansion (Option 4)
1. Add trend tracking (resolved per week, cumulative progress)
2. Add program-level breakdowns with drill-down
3. Add "inspection route" feature (group properties by geography for efficient site visits)
4. Make the summary report more detailed and formatted for leadership presentations

---

## Things Claude Code Should NEVER Do

1. **Never add FileMaker API connections.** No Data API calls, no session management, no field mapping to FM layouts. This tool is CSV-in, CSV-out. Period.
2. **Never deploy this publicly.** No Vercel, no Railway, no public URLs. This runs locally.
3. **Never add user authentication.** This is a single-user local tool. No Clerk, no JWT, no login pages.
4. **Never use marketing language in the UI.** No "Welcome to the Compliance Tracker!" No "Powered by AI." No "Smart" in user-facing labels unless it's genuinely descriptive. This is a government tool. Keep copy plain and functional.
5. **Never overstate detection capability.** Detection labels are "likely" not "confirmed." The tool triages, it does not assess. A human always makes the final call.
6. **Never create a buyer-facing interface.** This is an internal staff tool. Buyers never see it.
7. **Never add email sending capability.** Communication tracking logs what happened. It does not send emails. That's the existing workflow's job.
8. **Never use em dashes in any text, copy, comments, or documentation.** Use commas, semicolons, colons, or parentheses instead. This is a strict stylistic requirement.

---

## Things Claude Code SHOULD Do

1. **Prioritize the review workflow speed.** The person using this will process 20-50 properties per session. Every click, every load time, every navigation step matters. Minimize friction.
2. **Cache aggressively.** Images are expensive API calls. Once fetched, never re-fetch. Use disk cache with MD5-hashed filenames.
3. **Handle errors gracefully.** Google API will fail sometimes. Addresses will not geocode. Street View will not exist. The tool should continue working with partial data, not crash.
4. **Make exports FileMaker-friendly.** CSV column headers should be clean, consistent, and map easily to FileMaker field names. Include parcel ID as a key field for matching.
5. **Show the work.** Detection details should be transparent. Show the signal breakdown, not just the label. If the reviewer disagrees with the detection, they should be able to see why the algorithm scored it that way.
6. **Keep the codebase simple.** This is a tool Travis maintains. Avoid overengineering. Prefer explicit code over clever abstractions. Comment non-obvious logic.
7. **Test with Flint addresses.** When creating test data, use real Flint street patterns (numbered streets, named avenues, Genesee County parcel ID format XX-XX-XXX-XXX).

---

## Sample Test Data

Use these patterns for development and testing:

```csv
address,parcel_id,buyer_name,program,closing_date,commitment
307 Mason St,41-06-538-004,Derek Dohrman,Featured Homes,2024-03-15,$45000
1234 W Court St,41-11-234-012,Maria Santos,Ready for Rehab,2023-11-20,$80000
456 E Kearsley St,41-06-102-008,James Wilson,Featured Homes,2024-06-01,$35000
789 Saginaw St,41-06-441-015,Keisha Thompson,VIP Spotlight,2023-08-10,$120000
321 Crapo St,41-06-287-003,Robert Chen,Ready for Rehab,2024-01-22,$65000
1500 N Chevrolet Ave,41-08-155-009,Angela Davis,Featured Homes,2023-05-30,$42000
200 E Second St,41-06-078-011,Thomas Park,Ready for Rehab,2024-09-05,$95000
```

These are fictional entries using real Flint street patterns. The parcel ID format matches Genesee County conventions.

---

## Google Maps API Setup

1. Go to https://console.cloud.google.com
2. Create a project or select existing
3. Enable these APIs:
   - Street View Static API
   - Maps Static API
   - Geocoding API
4. Create an API key
5. Restrict the key to these three APIs only
6. Add the key to `backend/.env` as `GOOGLE_MAPS_API_KEY`

Free tier: $200/month credit covers roughly 14,000 Street View calls, 100,000 Static Maps calls, 40,000 Geocoding calls. A batch of 500 properties uses about 500 geocoding + 500 Street View + 500 satellite = 1,500 total calls. Well within free limits.

---

## Programs Reference

The Land Bank sells properties through these programs. Each has different compliance expectations:

- **Featured Homes:** Move-in ready properties sold as-is. Buyers agree to occupy and maintain. Compliance check: is the property occupied and maintained?
- **Ready for Rehab:** Properties requiring significant renovation. Buyers commit to a specific investment amount and timeline. Compliance check: has renovation occurred? Is committed investment reflected in improvements?
- **VIP Spotlight:** Unique properties evaluated through proposal submissions. Compliance varies by proposal terms.
- **Demolition:** Properties sold for demolition. Compliance check: has the structure been demolished?

Detection signals map differently to these programs. For example, "structure gone" is a problem for Featured Homes but may be expected for Demolition properties. The review interface should display the program so the reviewer has context when recording findings.
