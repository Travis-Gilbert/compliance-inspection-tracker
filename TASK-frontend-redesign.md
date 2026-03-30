# Compliance Tracker Frontend Redesign Spec

Complete form-and-function overhaul of the Next.js 15.3 frontend.
This spec covers UX improvements, visual design updates, component
decomposition, and new interaction patterns. Written as a Claude Code
task file with exact file paths, component specs, and verification steps.

## Governing Principles

1. **Staff throughput over dashboard vanity.** Every design decision
   prioritizes how fast Christina and Melissa can triage properties.
2. **Civic utilitarian aesthetic.** No SaaS gradients, no decorative
   motion. Dense, readable, government-tool honest.
3. **Progressive disclosure.** Show the 80% case by default. Tuck the
   20% behind a click, not a page load.
4. **Spatial reasoning first.** Staff think about properties by
   neighborhood. The map is a primary interface, not a dashboard widget.
5. **Keyboard-native.** Power users live on j/k/1-6. Every new feature
   must work without a mouse.
6. **No em dashes.** Anywhere. Ever. Comments, copy, documentation.

## Brand Tokens (unchanged, carried forward)

```
Primary:      civic green   #2E7D32
Accent:       civic blue    #1565C0
Background:   warm off-white #FAFAF5
Headings:     Bitter (serif)
Body:         IBM Plex Sans
Data/mono:    IBM Plex Mono
Status colors: traffic-light per finding severity
```

---

## Phase 1: Component Decomposition and Shared Infrastructure

### Task 1.1: Create shared types file

**File:** `frontend-next/src/lib/types.ts`

Create a single source of truth for TypeScript interfaces used across
all pages. Currently every component uses `any` for property data.

```ts
export interface Property {
  id: number;
  address: string;
  parcel_id: string | null;
  buyer_name: string | null;
  program: string | null;
  closing_date: string | null;
  commitment: string | null;
  finding: string | null;
  notes: string | null;
  detection_label: string | null;
  detection_score: number | null;
  compliance_status: string | null;
  tax_status: string | null;
  last_tax_payment: string | null;
  tax_amount_owed: number | null;
  homeowner_exemption: boolean | null;
  priority_score: number;
  latitude: number | null;
  longitude: number | null;
  formatted_address: string | null;
  streetview_available: boolean;
  streetview_date: string | null;
  satellite_path: string | null;
  reviewed_at: string | null;
  geocoded_at: string | null;
  created_at: string | null;
}

export interface Stats {
  total: number;
  reviewed: number;
  unreviewed: number;
  resolved: number;
  needs_inspection: number;
  percent_reviewed: number;
  by_finding: Record<string, number>;
  by_detection: Record<string, number>;
  by_compliance_status: Record<string, number>;
  unreviewed_by_detection: Record<string, number>;
}

export interface QueueResponse {
  properties: Property[];
  total: number;
}

export interface PipelineEvent {
  step: string;
  status?: string;
  total?: number;
  current?: number;
  processed?: number;
  attempted?: number;
  message?: string;
  grand_totals?: { total: number };
  grand_processed?: number;
}
```

**VERIFY:** `npx tsc --noEmit` passes with no errors referencing `any`
in property-related code after all components are updated to use these
types.

### Task 1.2: Extract reusable UI components

**Directory:** `frontend-next/src/components/ui/`

Create small, reusable components that are currently inline across
multiple pages.

#### `ui/Badge.tsx`
A general-purpose badge that replaces the 15+ inline badge `<span>`
elements scattered across review queue, property detail, and dashboard.

```tsx
interface BadgeProps {
  label: string;
  color: string;     // text color
  bg: string;        // background color
  size?: "sm" | "md";
  className?: string;
}
```

- `sm` size: `text-[11px] px-1.5 py-0.5`
- `md` size: `text-xs px-2 py-0.5`
- Always includes `font-medium rounded` base classes
- Accepts optional `className` for one-off overrides

#### `ui/StatCard.tsx`
Replaces the repeated stat card pattern on the dashboard.

```tsx
interface StatCardProps {
  label: string;
  value: number | string;
  accentColor?: string;   // left border color, defaults to gray-300
  subtitle?: string;      // small text below the value
  href?: string;          // if provided, wraps in a Link
}
```

- Uses `border-l-4` for the accent color
- `font-heading text-2xl font-bold` for the value
- `text-xs uppercase tracking-wide text-gray-500` for the label
- If `href` is provided, the entire card is a Next.js `Link` with
  `hover:border-gray-300` transition

#### `ui/FilterPill.tsx`
Toggle button used in filter bars.

```tsx
interface FilterPillProps {
  label: string;
  active: boolean;
  onClick: () => void;
  count?: number;   // shown as "(N)" suffix when provided
}
```

- Active state: `border-civic-green/20 bg-civic-green-pale text-civic-green`
- Inactive state: `border-gray-200 bg-white text-gray-600 hover:bg-gray-50`
- `text-xs font-medium rounded px-3 py-1.5`

#### `ui/EmptyState.tsx`
Consistent empty state pattern.

```tsx
interface EmptyStateProps {
  title: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  actionHref?: string;    // alternative to onAction for Link-based actions
}
```

- Centered layout inside `rounded-lg border border-gray-200 bg-white p-8`
- Title: `text-gray-600` in normal weight
- Message: `text-xs text-gray-400 mt-2`
- Action: styled as text link if present

#### `ui/SectionCard.tsx`
The white card container used everywhere on the dashboard and detail pages.

```tsx
interface SectionCardProps {
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;   // top-right slot for buttons/links
  children: React.ReactNode;
  className?: string;
  noPadding?: boolean;        // for content that needs edge-to-edge (maps, tables)
}
```

- Base: `rounded-lg border border-gray-200 bg-white`
- Padding: `p-5` unless `noPadding` is true
- Title: `font-heading font-semibold text-gray-900`
- Subtitle: `mt-1 text-sm text-gray-600`
- Action slot: positioned top-right with `flex items-start justify-between`

**VERIFY:** After extraction, search for inline badge/card patterns
across all pages. Each page should import from `components/ui/` instead
of defining its own inline styled spans.

---

## Phase 2: Navigation Redesign

### Task 2.1: Redesign the sidebar navigation

**File:** `frontend-next/src/app/(main)/layout.tsx`

**Current problems:**
- The `"use client"` directive on the layout is unnecessary if we extract
  the pathname-aware nav into a client component
- The two-letter abbreviations (DB, RQ, MP, IM, EX) are not conventional
  and add cognitive load
- Navigation items are flat when they should communicate hierarchy
- The footer disclaimer text is an afterthought

**Changes:**

1. Split into a server-component layout + client `Sidebar` component.

2. Replace the abbreviation badges with simple SVG icons. Each nav item
   gets a 16x16 icon from a minimal inline SVG set (no icon library
   dependency). Icons to use:
   - Dashboard: grid/squares icon
   - Review Queue: list/checklist icon
   - Compliance Map: map-pin icon
   - Import: upload icon
   - Export: download icon
   - Processing: play/gear icon (new route, see Phase 3)

3. Add visual grouping:
   - **Work** group: Dashboard, Review Queue, Compliance Map
   - **Data** group: Import, Export, Processing
   - Groups separated by a thin `border-t border-gray-100 mt-2 pt-2`
     with a `text-[10px] uppercase tracking-widest text-gray-400 px-3 mb-1`
     label

4. Active state: keep the current green highlight but add a subtle
   left-edge indicator (`border-l-2 border-civic-green`) in addition to
   the background color, so the active item is identifiable by position
   even without color perception.

5. Mobile: the current horizontal scroll nav is fine for small screens.
   Keep that pattern but apply the same icon + label treatment.

6. Remove the footer disclaimer text. Replace with the app version
   from `package.json` shown as `v2.0.0` in `text-[10px] text-gray-300`.

**New file:** `frontend-next/src/components/Sidebar.tsx` (client component)
**Updated file:** `frontend-next/src/app/(main)/layout.tsx` (becomes server component)

**Layout structure:**

```tsx
// layout.tsx (server component, no "use client")
import { Sidebar } from "@/components/Sidebar";

export default function MainLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      <Sidebar />
      <main className="flex-1 min-w-0">
        {children}
      </main>
    </div>
  );
}
```

Note: remove the `max-w-5xl mx-auto p-4 md:p-6` wrapper from the layout.
Each page should own its own max-width and padding, because the review
queue redesign needs full-width for the split-pane layout while the
dashboard wants a narrower content column.

**VERIFY:** Navigation renders correctly on mobile (horizontal scroll)
and desktop (vertical sidebar). Active states work for all routes
including nested routes like `/property/123`. No hydration warnings.

---

## Phase 3: Dashboard Redesign ("Briefing View")

### Task 3.1: Restructure the dashboard hierarchy

**File:** `frontend-next/src/app/(main)/page.tsx`

**Current problem:** The dashboard is a vertical stack of equal-weight
sections. When Christina opens the app, she has to scan the entire page
to figure out what needs attention. The pipeline controls take up
significant space and mix operational actions with monitoring.

**New information architecture (top to bottom):**

1. **Attention bar** (new): A single-line summary that answers "what
   needs my attention?" Compact, high-signal.

   ```
   [!] 42 properties need review | 3 non-compliant | 2 tax-delinquent    [Open Review Queue ->]
   ```

   - `rounded-lg border border-amber-200 bg-amber-50 px-4 py-3`
   - Uses amber/warning tone to draw the eye
   - The "Open Review Queue" link pre-filters to unreviewed
   - When everything is resolved: switches to a green success state
     with "All properties reviewed" message
   - This replaces the current progress bar as the primary status signal

2. **Review progress** (simplified): Keep the progress bar but make it
   more compact. Single line with percentage + bar + counts, not a
   full card.

   ```
   Review Progress ===========================--------  73%  (452 reviewed, 168 remaining)
   ```

   - No card wrapper. Just a `flex items-center gap-3` row
   - Progress bar: `h-2` instead of `h-3`, same green fill

3. **Summary stats row**: The four stat cards (Total, Resolved, Needs
   Inspection, Unreviewed), but with two changes:
   - Use `StatCard` component from Phase 1
   - Make each card a link: Total goes to full queue, Resolved goes to
     `?filter=resolved`, Needs Inspection goes to `?filter=inconclusive`,
     Unreviewed goes to `?filter=unreviewed`
   - The most important stat (Unreviewed or Needs Inspection, whichever
     is higher) gets a colored background instead of just a left border

4. **Compliance Map** (promoted): Move the Leaflet map UP to be the
   next thing after the stats. It is the most valuable visual on this
   page. Give it more height (`h-[500px]` instead of whatever it
   currently gets). Keep the property detail panel on hover/click.

5. **Compliance status breakdown**: Keep the 5-status row but make it
   collapsible. Default: expanded. Use a `details/summary` or a
   simple toggle so Christina can collapse it after she has internalized
   the numbers.

6. **Fast Review Lanes**: Keep these, they work well. Move them below
   the map. They serve as the bridge from "I see the big picture" to
   "now let me work the queue."

7. **Remove from dashboard:**
   - Pipeline controls (moved to `/processing` route, see Task 3.2)
   - Detection results breakdown (this is operational detail, not
     management monitoring; move to `/processing`)
   - Review Findings breakdown (available in the review queue filters)

### Task 3.2: Create Processing route

**New files:**
- `frontend-next/src/app/(main)/processing/page.tsx`
- `frontend-next/src/app/(main)/processing/loading.tsx`

Move all pipeline-related UI here:
- "Run Next Batch" and "Process All Remaining" buttons
- SSE pipeline progress display
- Google Maps API status indicator
- Detection results summary
- Review Findings summary

This page is the operational control panel. The dashboard is the
management overview. Separating them follows the principle of not mixing
monitoring with action on the same screen.

**Nav update:** Add "Processing" to the nav items in constants.ts:
```ts
{ path: "/processing", label: "Processing", shortLabel: "PR" },
```

Place it in the "Data" group in the sidebar, after Import.

**VERIFY:** Dashboard loads faster (fewer API calls: no imagery status,
no pipeline state). Processing page shows all pipeline controls. Links
between them work in both directions.

---

## Phase 4: Review Queue Redesign ("Triage Workstation")

This is the most impactful change. The review queue is where staff spend
80%+ of their time.

### Task 4.1: Split-pane master-detail layout

**File:** `frontend-next/src/app/(main)/review/page.tsx`

**Current pattern:** Property list with inline expansion. Clicking a
property navigates to `/property/[id]`, which loads a new page. User
must navigate back to continue reviewing.

**New pattern:** Split-pane layout at desktop widths. Left panel is the
property list (scrollable). Right panel shows the selected property's
imagery, metadata, and finding controls. Assigning a finding auto-
advances to the next property WITHOUT a page navigation.

**Layout structure:**

```
+--sidebar--+--------left panel---------+--------right panel--------+
|            | [filter bar, collapsible] | [selected property detail]|
| Dashboard  | [property list, scroll]  | [imagery side-by-side]    |
| Review  <- |  > 307 Mason St     [FH] | [detection info]          |
| Map        |    1234 W Court St  [RR] | [finding buttons]         |
| ...        |    456 E Kearsley   [FH] | [notes]                   |
|            |  > 789 Saginaw St   [VIP]| [external links]          |
+------------+--page/batch controls-----+---------------------------+
```

**Left panel specs:**
- Width: `w-[400px] flex-shrink-0` on desktop, full width on mobile
- Contains: filter bar (top), property list (scrollable middle),
  pagination (bottom sticky)
- Property rows are compact: address + buyer on one line, badges on
  second line. No thumbnail in the list view (thumbnails are in the
  detail panel). This increases density and lets staff scan faster.
- Selected property row gets `bg-civic-green-pale border-l-2 border-civic-green`
- Keyboard: j/k moves selection highlight, Enter opens in detail panel
  (already the default behavior since detail is inline)
- The list scrolls independently of the detail panel

**Right panel specs:**
- Takes remaining width: `flex-1 min-w-0`
- Sticky within viewport: `sticky top-0 h-screen overflow-y-auto`
- Contains everything currently on the `/property/[id]` page, adapted
  for inline display:
  - Property header (address, parcel, buyer, program badges)
  - Street View + Satellite images side-by-side
  - Detection alert bar
  - External links row (Street View interactive, Property Portal,
    Google Maps)
  - Finding buttons with keyboard shortcuts
  - Notes textarea with save
  - Tax info card
  - Outreach log
- When no property is selected: show an empty state with instructions
  ("Select a property from the list to begin review. Use j/k to
  navigate, 1-6 to assign findings.")

**Mobile behavior (below `lg` breakpoint):**
- Single column. The list is shown first.
- Tapping a property navigates to `/property/[id]` (existing page,
  kept as the mobile detail view).
- The split-pane layout only activates at `lg:` (1024px+).

**Component decomposition for the review page:**

```
frontend-next/src/components/review/
  ReviewLayout.tsx        -- split-pane shell, manages selected property state
  PropertyList.tsx        -- left panel: filter bar + scrollable list + pagination
  PropertyRow.tsx         -- single row in the list
  PropertyDetailPanel.tsx -- right panel: full property detail for inline review
  FilterBar.tsx           -- collapsible filter controls
  FindingButtons.tsx      -- the 6 finding buttons with keyboard hint labels
  BatchActionBar.tsx      -- sticky footer when items are selected
  FastLanes.tsx           -- the 5 fast-lane buttons (reused from dashboard)
```

### Task 4.2: Collapse the filter bar

**Component:** `frontend-next/src/components/review/FilterBar.tsx`

**Current problem:** 7 independent filter controls visible simultaneously.
This violates Hick's Law: too many choices for the common case.

**New pattern:**

Default visible controls (always shown):
- Filter pills: All | Unreviewed | Resolved | Needs Inspection
- Search input
- A "More filters" toggle button

Expanded state (after clicking "More filters"):
- Sort dropdown
- Program dropdown
- Detection dropdown
- Compliance status dropdown
- Tax status dropdown

The "More filters" button shows a count indicator when any advanced
filter is active: `"More filters (2)"` so the user knows filters are
applied even when the panel is collapsed.

**Keyboard shortcut:** `/` focuses the search input (standard convention
from GitHub, Slack, etc.). Add to the global keyboard handler.

### Task 4.3: Improve finding buttons interaction

**Component:** `frontend-next/src/components/review/FindingButtons.tsx`

**Changes:**
1. Show keyboard shortcut numbers as visible labels on each button,
   not hidden behind `md:inline`. Always visible.

2. After assigning a finding, auto-advance to the next property in the
   list (not via page navigation, just by updating the selected index).
   Show a brief toast-style confirmation: "Saved: Visibly Renovated.
   Moved to next." The toast auto-dismisses after 2 seconds.

3. Add an undo mechanism: for 5 seconds after assigning a finding, show
   an "Undo" link in the toast. Clicking it reverts the finding and
   re-selects that property.

4. The current toggle behavior (clicking the same finding again clears
   it) is good. Keep it.

### Task 4.4: Batch action bar

**Component:** `frontend-next/src/components/review/BatchActionBar.tsx`

When one or more properties are selected (via checkbox), show a sticky
bar at the bottom of the left panel:

```
+--[3 selected]--[Mark as: Renovated | Occupied | Vacant | ...]--[Clear]--+
```

- `sticky bottom-0` positioning
- `bg-white border-t border-gray-200 px-4 py-3 shadow-sm`
- Finding options shown as compact buttons in a row
- "Clear selection" as a text link on the right
- Confirmation dialog before batch update (existing behavior, keep it)

### Task 4.5: Keep the standalone property detail page

**File:** `frontend-next/src/app/(main)/property/[id]/page.tsx`

Do NOT delete this page. It serves two purposes:
1. Mobile detail view (when split-pane is not available)
2. Deep-linkable URL for sharing a specific property

But update it to use the same `PropertyDetailPanel` component as the
review queue's right panel. The standalone page just wraps it with
navigation controls (back button, prev/next) and its own page padding.

This means `PropertyDetailPanel` must be a pure presentational
component that receives a `Property` object and callbacks, not one that
fetches its own data. The standalone page and the review queue both
provide the data differently:
- Standalone page: fetches via `getProperty(id)` in a `useEffect`
- Review queue: passes the already-loaded property from the list state

**VERIFY:** Opening `/property/123` directly (bookmarked or shared link)
still works. The review queue split-pane shows the same content inline.
Keyboard shortcuts (1-6, arrows) work in both contexts.

---

## Phase 5: Map Improvements

### Task 5.1: Add filter integration to the Compliance Map

**File:** `frontend-next/src/app/map/page.tsx` (or wherever the
standalone map route lives)

**File:** `frontend-next/src/components/ManagementCoverageMap.tsx`

The map currently shows all properties with no filtering. Add a minimal
filter bar above the map:

- Program filter (dropdown): All | Featured Homes | Ready for Rehab | ...
- Compliance status filter (dropdown)
- Finding filter (dropdown)

When filters are applied, the map re-fetches from
`/api/properties/map/all` with the filter params (the API already
supports these params based on the `getMapProperties` function).

Pin colors should reflect the property's compliance status or finding,
not just a uniform blue. Use the status colors from the design tokens:
- Compliant: green
- In Progress: blue
- Needs Outreach: amber
- Non-Compliant: orange
- Unknown/Unreviewed: gray

### Task 5.2: Property detail panel on map click

The map's click-to-inspect behavior (shown in screenshot 2) is good.
Improve it:

1. When the "Before and After" images fail to load, show a fallback
   link: "View on Google Street View" that opens the interactive Street
   View in a new tab using the property's lat/lng.

2. Add a "Review this property" link that navigates to
   `/review?selected={id}` to open it in the split-pane review queue.

3. Show the detection score as a human-readable bar:
   ```
   Detection: Likely Occupied
   [===-------] 0.12 (low confidence)
   ```
   Map the 0-1 score to a verbal confidence label:
   - < 0.3: "low confidence"
   - 0.3-0.6: "moderate confidence"  
   - > 0.6: "high confidence"

---

## Phase 6: Import/Export Improvements

### Task 6.1: Post-import pipeline prompt

**File:** `frontend-next/src/app/(main)/import/page.tsx`

After a successful CSV import, add a call-to-action:

```
[success banner] Imported 47 properties.

Would you like to run the processing pipeline on these properties now?
This will geocode addresses, fetch Street View imagery, and run
vacancy detection.

[Run Pipeline Now]   [Skip, I will process later]
```

"Run Pipeline Now" navigates to `/processing` and auto-starts the
pipeline (via a query param like `?autostart=true`).

"Skip" stays on the import page.

### Task 6.2: Simplify export page

**File:** `frontend-next/src/app/(main)/export/page.tsx`

The export page should show 4 download options as a clean card layout:

1. **Full CSV Export** (all properties, all columns)
2. **Inspection List** (properties marked "Needs Inspection" only)
3. **Resolved Properties** (all desk-resolved properties)
4. **Summary Report** (text summary with counts)

Each card shows: title, one-line description of what is included, and a
download button. No additional controls needed.

---

## Phase 7: Accessibility Fixes

### Task 7.1: Color-plus-text for all status indicators

**All components using status colors**

Every status indicator that currently relies on color alone must also
include a text label or icon. Audit:

- Compliance status badges: already have text, OK
- Detection badges: already have text, OK  
- Finding badges: already have text, OK
- Stat card left borders: no text equivalent. Fix by ensuring the card
  label text communicates the status, not just the border color.
- Map pins: currently uniform blue. When we add colored pins (Phase 5),
  each pin must have a tooltip showing the status text on hover.

### Task 7.2: Focus management in split-pane

When the user presses j/k to navigate the property list, focus must
move to the selected row. The detail panel should update but NOT steal
focus from the list. The user should be able to keep pressing j/k
without the focus jumping to the right panel.

When the user presses 1-6 to assign a finding, the finding is saved
and the selection advances. Focus stays on the list.

When the user presses Enter on a selected row, focus moves to the
detail panel (specifically, to the first finding button). Pressing
Escape returns focus to the list at the previously selected index.

### Task 7.3: ARIA landmarks

- The sidebar: `<nav aria-label="Main navigation">`
- The property list: `role="listbox"` with `role="option"` on each row
- The detail panel: `<section aria-label="Property detail">`
- The filter bar: `<form role="search">`
- Finding buttons: `role="radiogroup"` with `role="radio"` on each button

### Task 7.4: Skip link

Add a skip link as the first focusable element in the layout:

```html
<a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-white focus:px-4 focus:py-2 focus:rounded focus:shadow-lg">
  Skip to main content
</a>
```

The main content area gets `id="main-content"`.

---

## Phase 8: Performance and Code Quality

### Task 8.1: Break the 31KB review page into components

The current `review/page.tsx` is 31KB and handles:
- URL search param sync
- Data fetching
- Keyboard navigation
- Filter state
- Selection state  
- Batch operations
- Property list rendering
- Expanded preview rendering

After Phase 4, this file should be under 5KB. It becomes a thin
orchestrator that:
1. Manages the selected property ID
2. Delegates filtering/fetching to `PropertyList`
3. Delegates detail display to `PropertyDetailPanel`
4. Sets up global keyboard listeners

### Task 8.2: Extract keyboard navigation into a custom hook

**File:** `frontend-next/src/hooks/useReviewKeyboard.ts`

Move all keyboard handling out of inline `useEffect` blocks and into
a dedicated hook:

```ts
interface UseReviewKeyboardOptions {
  properties: Property[];
  focusedIndex: number;
  setFocusedIndex: (fn: (i: number) => number) => void;
  onFindingAssign: (id: number, finding: string) => void;
  onNavigateToProperty: (id: number) => void;
  onEscape: () => void;
}
```

This hook handles: j/k navigation, 1-6 finding assignment, Enter to
open detail, Escape to go back, / to focus search.

### Task 8.3: Move data fetching into custom hooks

**File:** `frontend-next/src/hooks/useReviewQueue.ts`

Encapsulate the queue data fetching, pagination, and URL sync logic:

```ts
interface UseReviewQueueReturn {
  properties: Property[];
  totalCount: number;
  stats: Stats | null;
  loading: boolean;
  error: string;
  page: number;
  filters: ReviewFilters;
  setFilters: (filters: Partial<ReviewFilters>) => void;
  setPage: (page: number) => void;
  refresh: () => Promise<void>;
}
```

This hook owns the URL search param synchronization, debounced search,
and the `loadProperties` callback.

---

## Implementation Order

Execute phases in order. Within each phase, execute tasks in order.
Each phase should be a separate commit (or set of commits).

| Phase | Description | Estimated Scope |
|-------|-------------|-----------------|
| 1 | Types + shared UI components | Small, foundational |
| 2 | Navigation redesign | Medium, layout changes |
| 3 | Dashboard restructure + Processing route | Medium |
| 4 | Review Queue split-pane | Large, core UX change |
| 5 | Map improvements | Medium |
| 6 | Import/Export refinements | Small |
| 7 | Accessibility | Medium, cross-cutting |
| 8 | Code quality + hooks extraction | Medium, refactoring |

Phases 1-2 can be done quickly and improve the codebase for everything
after. Phase 4 is the biggest and most impactful change. Phase 8 can
happen concurrently with any other phase as refactoring opportunities
arise.

---

## Files to Create (new)

```
frontend-next/src/lib/types.ts
frontend-next/src/hooks/useReviewKeyboard.ts
frontend-next/src/hooks/useReviewQueue.ts
frontend-next/src/components/ui/Badge.tsx
frontend-next/src/components/ui/StatCard.tsx
frontend-next/src/components/ui/FilterPill.tsx
frontend-next/src/components/ui/EmptyState.tsx
frontend-next/src/components/ui/SectionCard.tsx
frontend-next/src/components/Sidebar.tsx
frontend-next/src/components/review/ReviewLayout.tsx
frontend-next/src/components/review/PropertyList.tsx
frontend-next/src/components/review/PropertyRow.tsx
frontend-next/src/components/review/PropertyDetailPanel.tsx
frontend-next/src/components/review/FilterBar.tsx
frontend-next/src/components/review/FindingButtons.tsx
frontend-next/src/components/review/BatchActionBar.tsx
frontend-next/src/components/review/FastLanes.tsx
frontend-next/src/app/(main)/processing/page.tsx
frontend-next/src/app/(main)/processing/loading.tsx
```

## Files to Modify (existing)

```
frontend-next/src/app/(main)/layout.tsx          -- extract Sidebar, remove "use client"
frontend-next/src/app/(main)/page.tsx             -- dashboard briefing view redesign
frontend-next/src/app/(main)/review/page.tsx      -- split-pane layout, decompose
frontend-next/src/app/(main)/property/[id]/page.tsx -- use shared PropertyDetailPanel
frontend-next/src/app/(main)/import/page.tsx      -- post-import pipeline prompt
frontend-next/src/app/(main)/export/page.tsx      -- simplified card layout
frontend-next/src/lib/constants.ts                -- add Processing nav item
frontend-next/src/components/ManagementCoverageMap.tsx -- filter integration, colored pins
frontend-next/src/components/LoadingSkeleton.tsx   -- add skeletons for new layouts
```

## Files to Delete (after migration)

None. All existing files are modified in place or supplemented by new
components. The property detail page is kept for mobile and deep links.

---

## Verification Checklist

After all phases are complete, verify:

- [ ] `npx tsc --noEmit` passes (no type errors)
- [ ] `npm run build` completes (no build errors)
- [ ] Dashboard loads in under 2 seconds with 620 properties
- [ ] Review queue split-pane shows property detail without page navigation
- [ ] j/k navigation works in the property list
- [ ] 1-6 finding assignment works, auto-advances, shows toast
- [ ] Batch selection with checkbox + batch finding update works
- [ ] Filter bar collapses and expands, advanced filters toggle works
- [ ] `/` shortcut focuses the search input
- [ ] Map shows filtered properties with color-coded pins
- [ ] Map click shows property detail with working imagery
- [ ] Import page shows pipeline prompt after successful import
- [ ] Processing page shows pipeline controls and progress
- [ ] Mobile layout falls back to single-column with page navigation
- [ ] All status indicators use color + text (not color alone)
- [ ] Focus management follows the keyboard model described in 7.2
- [ ] Skip link works
- [ ] ARIA landmarks are present on all major page regions
