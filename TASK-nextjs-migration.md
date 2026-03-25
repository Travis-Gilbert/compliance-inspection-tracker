# Task: Migrate Compliance Tracker Frontend from Vite+React to Next.js

## Context

The compliance inspection tracker frontend (`frontend/` directory in
`Travis-Gilbert/compliance-inspection-tracker`) is a Vite+React SPA that talks to a
FastAPI backend. We are migrating to Next.js (App Router) for better developer velocity,
access to the shadcn/ui component ecosystem, and deployment on Vercel.

The FastAPI backend (`backend/`) is NOT changing. The Next.js app is client-only in terms
of data fetching (all data comes from the FastAPI API). We are not using Next.js SSR or
Server Components for data. All pages are "use client" because they have heavy
interactivity (maps, forms, state).

**Repo:** `Travis-Gilbert/compliance-inspection-tracker`
**Current deploy:** Vercel project "frontend" (team: `team_kScZ3GDZWV8zuG3fk5zlWxVB`)
**Backend API:** FastAPI at `http://127.0.0.1:8000` locally, environment variable for production

## Hard Rules

1. Never connect to FileMaker. CSV-in, CSV-out only.
2. Never use marketing language in the UI. Government tool, plain copy.
3. Never use em dashes in text, copy, comments, or documentation.
4. Detection is triage, not assessment. The human reviewer makes the final call.
5. `font-mono` restricted to parcel IDs, dollar amounts, and reference numbers only.
6. Design tokens: Bitter (headings), IBM Plex Sans (body), IBM Plex Mono (data).
7. Colors: civic green `#2E7D32`, civic blue `#1565C0`, warm off-white `#FAFAF5`.

## Steps 1-14: See full task file

The complete 14-step migration is available in the Claude conversation and as a
downloaded file (TASK-nextjs-migration.md). Key steps:

1. Scaffold Next.js in `frontend-next/` (create-next-app with TypeScript, Tailwind, App Router)
2. Copy Tailwind config (civic/warm/status colors, Bitter/IBM Plex fonts)
3. Set up shadcn/ui (button, card, badge, table, tabs, select, input, textarea, dialog, dropdown-menu, separator, skeleton, toast)
4. Configure next.config.ts rewrites for FastAPI proxy (/api/*, /images/*)
5. Migrate api.ts (replace import.meta.env with empty base, add TS types)
6. Migrate constants.ts (add TS interfaces)
7. Create route structure using App Router (route group `(main)` for sidebar pages, `/map` outside)
8. Root layout (next/font/google for Bitter, IBM Plex Sans, IBM Plex Mono)
9. Sidebar layout in `(main)/layout.tsx` (usePathname for active state)
10. Migrate all 6 pages ("use client", fix react-router to next/navigation imports)
11. Error and loading boundaries (error.tsx, loading.tsx per route)
12. Install Leaflet deps, use next/dynamic with ssr:false for map pages
13. Update Vercel settings (framework: Next.js, root: frontend)
14. Add new data fields post-migration (compliance_status, tax_status, outreach tracking, homeowner_exemption)

## Route Structure

```
src/app/
  layout.tsx              # Root (html, body, fonts, metadata)
  (main)/                 # Route group: pages WITH sidebar
    layout.tsx            # Sidebar
    page.tsx              # Dashboard
    review/page.tsx       # ReviewQueue
    property/[id]/page.tsx # PropertyDetail
    import/page.tsx       # Import
    export/page.tsx       # Export
  map/
    page.tsx              # LeadershipMap (no sidebar, full bleed)
```

## File Mapping

| Old | New | Notes |
|---|---|---|
| src/main.jsx | DELETED | App Router |
| src/App.jsx | DELETED | File-based routing |
| src/utils/api.js | src/lib/api.ts | Fix env var |
| src/utils/constants.js | src/lib/constants.ts | Add types |
| src/components/Layout.jsx | src/app/(main)/layout.tsx | usePathname |
| src/components/ErrorBoundary.jsx | error.tsx per route | Next.js pattern |
| src/components/LoadingSkeleton.jsx | loading.tsx per route | Split out |
| src/pages/Dashboard.jsx | src/app/(main)/page.tsx | "use client" |
| src/pages/ReviewQueue.jsx | src/app/(main)/review/page.tsx | Fix searchParams |
| src/pages/PropertyDetail.jsx | src/app/(main)/property/[id]/page.tsx | Fix useParams |
| src/pages/Import.jsx | src/app/(main)/import/page.tsx | Direct copy |
| src/pages/Export.jsx | src/app/(main)/export/page.tsx | Direct copy |
| src/pages/LeadershipMap.jsx | src/components/LeadershipMap.tsx | dynamic(), ssr:false |
| vite.config.js | next.config.ts | Rewrites |
| vercel.json | DELETED | Next.js handles routing |
