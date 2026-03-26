# Feature Handoff: Compliance Tracker Next.js Migration

## Requirements

Migrate the compliance inspection tracker frontend from Vite + React Router to
Next.js 15 App Router with shadcn/ui. The app is a desk-research triage tool for
GCLBA compliance staff reviewing 620+ sold properties via Google Street View imagery.

Users: 3-5 internal staff (Christina, Melissa, Travis, compliance team).
Deploy target: Vercel (project `frontend`, team `team_kScZ3GDZWV8zuG3fk5zlWxVB`).
Backend: FastAPI at `http://127.0.0.1:8000` locally. Unchanged by this migration.

## Environment

- Repo: `Travis-Gilbert/compliance-inspection-tracker`
- Current frontend: `frontend/` (Vite 6, React 18, React Router 6, Tailwind 3, Leaflet)
- Target: Next.js 15+ (App Router, TypeScript, Tailwind, shadcn/ui)
- Node: 24.x (Vercel default)
- Backend: FastAPI + SQLite (separate `backend/` directory, NOT changing)

## Hard Rules

1. Never connect to FileMaker. CSV-in, CSV-out only.
2. Never use marketing language. Government tool, plain copy.
3. Never use em dashes in text, copy, comments, or documentation.
4. Detection is triage, not assessment. Human reviewer makes the final call.
5. `font-mono` restricted to parcel IDs, dollar amounts, reference numbers only.
6. Design tokens: Bitter (headings), IBM Plex Sans (body), IBM Plex Mono (data).
7. Civic green `#2E7D32`, civic blue `#1565C0`, warm off-white `#FAFAF5`.

## Route Structure

```
frontend-next/src/
  app/
    layout.tsx                          # Root: html, body, next/font, metadata
    globals.css                         # Tailwind directives + shadcn CSS vars
    (main)/                             # Route group: pages WITH sidebar
      layout.tsx                        # Sidebar nav ("use client", usePathname)
      page.tsx                          # Dashboard
      loading.tsx                       # DashboardSkeleton
      error.tsx                         # Shared error boundary
      review/
        page.tsx                        # ReviewQueue
        loading.tsx                     # ReviewQueueSkeleton
      property/
        [id]/
          page.tsx                      # PropertyDetail
          loading.tsx                   # PropertyDetailSkeleton
      import/
        page.tsx                        # CSV Import
      export/
        page.tsx                        # CSV Export
    map/
      page.tsx                          # LeadershipMap (no sidebar, full bleed)
      error.tsx
  components/
    LeadershipMap.tsx                    # Leaflet map (imported via dynamic ssr:false)
    ManagementCoverageMap.tsx            # Leaflet coverage map (same treatment)
    InlineNotice.tsx                     # Alert/notice component
  lib/
    api.ts                              # FastAPI client (all fetch functions)
    constants.ts                        # FINDINGS, NAV_ITEMS, PROGRAMS, etc.
```

## Rendering Strategy

Every page is `"use client"` with client-side data fetching via `useEffect`.
No SSR, no Server Components for data. Justification: all pages use heavy
browser APIs (Leaflet, SSE streaming, FormData uploads, URL search params).
The FastAPI backend is the single data source, accessed via rewrites.

This is intentional. SSR would add complexity with zero benefit for an internal
staff tool with 3-5 users and no SEO requirements.

## Data Flow

### Source
All data flows from the FastAPI backend via `/api/*` endpoints.

### Local Dev
Next.js `rewrites` in `next.config.ts` proxy `/api/*` and `/images/*` to
`http://127.0.0.1:8000`.

### Production (Vercel)
Environment variable `NEXT_PUBLIC_API_URL` points to the Railway-deployed
FastAPI backend. Rewrites forward to that URL.

```ts
// next.config.ts
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/images/:path*", destination: `${API_URL}/images/:path*` },
    ];
  },
};
```

### Caching
No server-side caching. All data is fetched client-side per page load.
The FastAPI backend handles its own caching where needed.

### Mutations
All mutations are client-side POST/PATCH via the api.ts client.
No Server Actions (everything is "use client").

## Component Boundaries

### Server Components (no "use client")
- `app/layout.tsx` (root layout, metadata, fonts)

### Client Components ("use client")
- `app/(main)/layout.tsx` (sidebar, needs usePathname)
- All 6 page.tsx files (hooks, state, browser APIs)
- All error.tsx files (needs reset callback)
- `components/LeadershipMap.tsx` (Leaflet)
- `components/ManagementCoverageMap.tsx` (Leaflet)

## Files to Create

### app/layout.tsx (Server Component)
Root layout. Loads Bitter, IBM Plex Sans, IBM Plex Mono via `next/font/google`.
Sets CSS variables `--font-heading`, `--font-body`, `--font-mono` on `<body>`.
Applies `bg-warm-100 text-gray-900 font-body antialiased`.
Sets metadata title "Compliance Inspection Tracker | GCLBA".
Inline SVG favicon (green bar chart icon, existing from `frontend/index.html`).

### app/(main)/layout.tsx ("use client")
Sidebar navigation. Migrated from `frontend/src/components/Layout.jsx`.
Replace `NavLink` from react-router with `Link` from next/link.
Replace `isActive` callback with `usePathname()` comparison.
`Outlet` replaced by `{children}` prop.

### app/(main)/page.tsx ("use client") [Dashboard]
Source: `frontend/src/pages/Dashboard.jsx` (17,081 bytes).
Import changes only: `@/lib/api`, `@/lib/constants`.
No routing hooks used. SSE streaming (`runPipelineStream`) works as-is.

### app/(main)/review/page.tsx ("use client") [ReviewQueue]
Source: `frontend/src/pages/ReviewQueue.jsx` (24,792 bytes).
Replace `useSearchParams` from react-router with `useSearchParams` from
`next/navigation`. Key difference: Next.js returns `ReadonlyURLSearchParams`.
To update params, use `useRouter().push()` with constructed URL string.
Replace `Link` import from react-router with `next/link`.

### app/(main)/property/[id]/page.tsx ("use client") [PropertyDetail]
Source: `frontend/src/pages/PropertyDetail.jsx` (17,987 bytes).
Replace `useParams()` from react-router (same name, different import).
Replace `useNavigate()` with `useRouter()`:
  `navigate(-1)` becomes `router.back()`
  `navigate('/property/${id}')` becomes `router.push('/property/${id}')`
Replace `Link` import.

### app/(main)/import/page.tsx ("use client") [Import]
Source: `frontend/src/pages/Import.jsx` (10,440 bytes).
No routing hooks. Fix imports only.

### app/(main)/export/page.tsx ("use client") [Export]
Source: `frontend/src/pages/Export.jsx` (4,551 bytes).
No routing hooks. Fix imports only.

### app/map/page.tsx ("use client") [LeadershipMap]
Thin wrapper using `next/dynamic` with `ssr: false`:
```tsx
"use client";
import dynamic from "next/dynamic";
const LeadershipMap = dynamic(() => import("@/components/LeadershipMap"), {
  ssr: false,
  loading: () => (
    <div className="h-screen w-full flex items-center justify-center bg-warm-50">
      <p className="text-gray-500 text-sm">Loading map...</p>
    </div>
  ),
});
export default function MapPage() {
  return <LeadershipMap />;
}
```
The actual component moves to `components/LeadershipMap.tsx`.
Same treatment for `ManagementCoverageMap.tsx`.
Import `leaflet/dist/leaflet.css` inside the component (not globally).

### lib/api.ts
Source: `frontend/src/utils/api.js` (7,214 bytes).
Replace `import.meta.env.VITE_API_BASE_URL` with empty string `""`.
Rewrites handle proxying, so all URLs are relative (`/api/properties/`).
Add TypeScript annotations to all function params and returns.
Keep all function signatures identical. SSE streaming works as-is.

### lib/constants.ts
Source: `frontend/src/utils/constants.js` (2,719 bytes).
Direct copy with TypeScript interfaces added:
```ts
export interface Finding { value: string; label: string; color: string; bg: string; }
export interface NavItem { path: string; label: string; shortLabel: string; }
export interface FastLane { id: string; label: string; description: string; params: Record<string, string>; }
```

## Loading & Error States

### Loading
- `app/(main)/loading.tsx`: DashboardSkeleton (from LoadingSkeleton.jsx)
- `app/(main)/review/loading.tsx`: ReviewQueueSkeleton
- `app/(main)/property/[id]/loading.tsx`: PropertyDetailSkeleton

### Error
- `app/(main)/error.tsx`: Shared error boundary for all (main) routes.
  Migrated from `ErrorBoundary.jsx`. Uses Next.js `error` + `reset` props.
  Civic green "Try Again" button. Shows `error.message`.
- `app/map/error.tsx`: Same pattern, isolated for map route.

## Metadata

```ts
export const metadata: Metadata = {
  title: "Compliance Inspection Tracker | GCLBA",
  description: "Desk research triage tool for GCLBA compliance staff.",
  icons: {
    icon: "data:image/svg+xml,...", // existing green bar chart SVG
  },
};
```

No OG images needed (internal tool, no social sharing).

## Scaffold Commands

```bash
npx create-next-app@latest frontend-next \
  --typescript --tailwind --eslint --app --src-dir \
  --import-alias "@/*" --use-npm

cd frontend-next
npx shadcn@latest init  # Style: Default, Base: Neutral, CSS vars: Yes
npx shadcn@latest add button card badge table tabs select input \
  textarea dialog dropdown-menu separator skeleton toast

npm install leaflet react-leaflet
npm install -D @types/leaflet
```

## Tailwind Config

Copy `theme.extend` from `frontend/tailwind.config.js` into
`frontend-next/tailwind.config.ts`. Key change: font families reference
CSS variables from next/font instead of direct names:

```ts
fontFamily: {
  heading: ["var(--font-heading)", "Georgia", "serif"],
  body: ["var(--font-body)", "-apple-system", "sans-serif"],
  mono: ["var(--font-mono)", "monospace"],
},
```

Preserve all custom colors: civic.*, warm.*, status.*, detection.*.

## Import Translation Table

Every file needs these import swaps:

| Old Import | New Import |
|---|---|
| `from "react-router-dom"` (Link) | `from "next/link"` |
| `from "react-router-dom"` (useParams) | `from "next/navigation"` |
| `from "react-router-dom"` (useNavigate) | `from "next/navigation"` (useRouter) |
| `from "react-router-dom"` (useSearchParams) | `from "next/navigation"` |
| `from "react-router-dom"` (NavLink) | `from "next/link"` (Link) |
| `from "react-router-dom"` (Outlet) | children prop |
| `../utils/api` | `@/lib/api` |
| `../utils/constants` | `@/lib/constants` |
| `../components/Layout` | DELETED (now a layout.tsx) |
| `../components/ErrorBoundary` | DELETED (now error.tsx) |
| `../components/LoadingSkeleton` | DELETED (now loading.tsx per route) |
| `../components/InlineNotice` | `@/components/InlineNotice` |

## API Hook Translation

| react-router-dom | next/navigation | Notes |
|---|---|---|
| `useNavigate()` | `useRouter()` | |
| `navigate("/path")` | `router.push("/path")` | |
| `navigate(-1)` | `router.back()` | |
| `navigate(path, { replace: true })` | `router.replace(path)` | |
| `useParams()` | `useParams()` | Same API, different import |
| `useSearchParams()` | `useSearchParams()` | Returns ReadonlyURLSearchParams in Next.js |
| `setSearchParams(params)` | `router.push("?" + params.toString())` | Next.js searchParams are read-only |

## Deployment

1. Complete migration, verify locally with FastAPI backend running
2. Delete `frontend/` directory
3. Rename `frontend-next/` to `frontend/`
4. Update Vercel project settings: Framework: Next.js, Root: `frontend`
5. Set env var `NEXT_PUBLIC_API_URL` to FastAPI Railway URL
6. Push to main. Vercel auto-builds.

## Verification

- [ ] `npm run build` succeeds
- [ ] Dashboard loads stats, pipeline SSE streaming works
- [ ] ReviewQueue filters, batch update, image thumbnails work
- [ ] PropertyDetail loads by ID, prev/next navigation works
- [ ] Import: CSV upload works
- [ ] Export: all download links produce valid CSVs
- [ ] LeadershipMap: Leaflet renders with heat map data
- [ ] Sidebar highlights active route correctly
- [ ] `/map` has no sidebar (full-bleed layout)
- [ ] Error boundaries display with "Try Again" button
- [ ] Loading skeletons appear during data fetch
- [ ] Fonts: Bitter headings, IBM Plex Sans body, no FOUT
- [ ] Vercel deploy succeeds
- [ ] shadcn/ui components render correctly

## Post-Migration: New Data Fields

After stable migration, add fields Christina requested (separate task):

| Field | Type | Purpose |
|---|---|---|
| compliance_status | enum | compliant, in_progress, needs_outreach, non_compliant, unknown |
| tax_status | enum | current, delinquent, payment_plan, unknown |
| last_tax_payment | date | Most recent tax payment |
| tax_amount_owed | decimal | Outstanding balance |
| outreach_attempts | int | Contact attempt count |
| last_outreach_date | date | When last contacted |
| outreach_method | enum | email, phone, mail, in_person |
| homeowner_exemption | bool | Whether exemption is filed |

New shadcn components: ComplianceStatusBadge (Badge), TaxInfoCard (Card),
OutreachLog (Table + Dialog), ComplianceFilters (Select dropdowns),
FileMaker Export CSV option on Export page.
