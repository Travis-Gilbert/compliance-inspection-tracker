# Design

## Visual Theme

Compliance Tracker uses a civic utilitarian interface: high-density operational screens, clear evidence surfaces, quiet chrome, and restrained color. The physical scene is a staff member reviewing property records at a desk in office lighting, moving quickly between search, imagery, upload, and export tasks. Light surfaces fit that setting best.

## Color Palette

Use a restrained product palette. Existing hex values may remain in Tailwind config, but new authored colors should prefer OKLCH where practical.

- Page: warm off-white `#FAFAF5`
- Primary action: civic green `#2E7D32`
- Secondary action: civic blue `#1565C0`
- Text: near-black tinted neutral, never pure black
- Surface: warm white tinted neutral, never pure white
- Status: traffic-light severity roles for compliant, partial, vacant, gone, and inconclusive findings

Accent color is for primary actions, current navigation, focus states, and state indicators. It is not decorative.

## Typography

- Headings: Bitter where already used by the app
- Body: IBM Plex Sans
- Data: IBM Plex Mono
- Keep labels, buttons, and dense UI copy compact and readable
- Avoid display-scale type inside cards, lists, tables, and tool panels
- Keep prose line length near 65 to 75 characters

## Components

- App shell: persistent top navigation with global address search
- Evidence cards: large before and after image surfaces, with address, program, status, and photo completeness close to the imagery
- Upload zones: always name the destination property and side before upload
- Search: keyboard accessible, ranked by address, parcel ID, buyer, and organization
- Map layers: precise pins plus compliant and non-compliant density layers
- Buttons and form controls: consistent default, hover, focus, active, disabled, loading, and error states

Cards should represent individual records or focused tools only. Do not put cards inside other cards.

## Layout

Use predictable grids and route-level structure. The dashboard is an operations summary, not a visual showcase. The Before and After page is the main evidence gallery. Property detail, review queue, and gallery cards should share the same photo evidence vocabulary.

Responsive behavior should preserve evidence size first: images remain useful, controls stack predictably, and text must not overlap or truncate critical address information.

## Motion

Use motion only for state feedback, search result reveal, upload progress, and map layer transitions. Prefer 150 to 250 ms ease-out transitions. Do not animate layout properties.

## Copy

Use plain government-tool copy. Avoid marketing, AI claims, certainty inflation, and em dashes. Detection language must stay in the "likely" register and manual findings must remain the source of compliance decisions.
