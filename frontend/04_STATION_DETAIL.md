# FloodGuard Penang — Shared UI Design System

## 1. Visual direction

Use a minimalist, modern, fluid environmental-monitoring dashboard inspired by the latest FloodGuard reference images.

- Light theme only.
- Large rounded desktop application shell on a soft neutral outer background.
- White and off-white surfaces.
- Restrained blue primary color.
- Green, amber, orange and red only for meaningful operational states.
- Soft 1 px borders and very subtle elevation.
- Generous whitespace without making the interface sparse.
- Clean outline icons from one icon family, preferably Lucide.
- No glassmorphism, neon glow, decorative gradients, oversized icons, or generic SaaS decoration.

## 2. Core palette

| Token | Value | Usage |
|---|---|---|
| Canvas | `#ECEFF3` | Outer page background |
| App surface | `#FFFFFF` | Main application shell |
| Sidebar | `#FBFCFE` | Sidebar background |
| Panel | `#FFFFFF` | Cards / tables / panels |
| Panel subtle | `#F8FAFC` | Secondary panel areas |
| Border | `#E4E7EC` | Dividers and panel borders |
| Text primary | `#101828` | Headings and important values |
| Text secondary | `#667085` | Labels and metadata |
| Primary blue | `#2563EB` | Active nav, links, buttons |
| Primary subtle | `#EAF2FF` | Selected navigation / rows |
| Telemetry blue | `#0EA5E9` | Observed water / rainfall visuals |
| Normal | `#22C55E` | Normal / healthy |
| Waspada | `#FBBF24` | Caution |
| Amaran | `#F97316` | Warning |
| Bahaya | `#EF4444` | Danger |
| FloodGuard derived | `#7C3AED` | Model-derived/source distinction where needed |

## 3. Typography

Use:

```css
font-family: "Inter", "Geist", "SF Pro Text", "Segoe UI", sans-serif;
```

Recommended scale:

- Page title: 28–32 px, 600–700
- Section title: 18–20 px, 600
- Panel title: 16–18 px, 600
- Body: 14–16 px
- Table text: 13–14 px
- Metadata: 12–13 px

Use tabular numerals for:

- water level
- rainfall
- percentages
- timestamps
- prediction horizons
- station counts

## 4. Application shell

Desktop reference: approximately 1600–1900 px wide.

- Outer canvas: soft neutral gray.
- App shell:
  - white background
  - 28–36 px outer radius
  - subtle large soft shadow
  - overflow hidden
- Sidebar:
  - 220–240 px wide
  - white / off-white
  - right divider
  - compact FloodGuard Penang brand at top
  - navigation in a single vertical column
  - persistent disclaimer at bottom
- Header:
  - 72–84 px
  - title and subtitle left
  - last-updated time + refresh + contextual selector right
  - no avatar, notification bell, global search, or theme switcher

## 5. Navigation

Primary items:

1. Overview
2. Live Map
3. Stations
4. Predictions
5. Alerts
6. Data Status

Selected item:

- light blue background
- blue 2 px accent on left or right edge
- blue icon
- dark label
- 10–12 px radius

## 6. Panels and cards

- Radius: 14–18 px
- Border: `1px solid #E4E7EC`
- Static panels: no heavy shadow
- Important hero panel may use a photo/map background with dark translucent information overlay
- Panel padding: 20–24 px
- Internal spacing: 16–24 px
- Avoid deep nesting

## 7. Icons

Use Lucide or an equivalent single outline family.

Suggested mapping:

| Concept | Icon |
|---|---|
| Overview | `House` / `LayoutDashboard` |
| Live map | `Map` |
| Stations | `MapPin` |
| Predictions | `ChartLine` |
| Alerts | `Bell` |
| Data status | `Database` |
| Water level | `Waves` |
| Rainfall | `CloudRain` |
| Freshness | `Clock3` |
| Refresh | `RefreshCw` |
| Official source | `Landmark` |
| Model / prediction | `BrainCircuit` or `ChartSpline` |

Icon size:

- nav: 18–20 px
- buttons: 16–18 px
- status: 14–16 px
- large metric icon: max 28–32 px

## 8. Controls

- Input/select height: 40–44 px
- Radius: 10–12 px
- White surface
- 1 px border
- Visible hover and focus states
- Focus ring: 2 px primary blue
- Primary button: blue fill, white text
- Secondary button: white fill, border, blue/dark text

## 9. Tables

- White surface
- Sticky header when useful
- Header background `#F8FAFC`
- Row height around 44–52 px
- Thin row dividers
- No zebra stripes
- Hover: light gray/blue
- Selected row: subtle blue
- Status uses small labeled chips
- Numeric columns use tabular numerals

## 10. Status styling

Never use color alone.

- Normal: green + label/icon
- Waspada: amber + label/icon
- Amaran: orange + label/icon
- Bahaya: red + label/icon
- Fresh: green dot + text
- Delayed: amber dot + text
- Stale: orange/red dot + text
- No data: gray dot + text

## 11. Source semantics

Keep these visually distinct:

### JPS observed / official

- Label clearly as `JPS observed`, `Official JPS state`, or `Official JPS thresholds`
- Blue telemetry visuals for observed data
- Waspada / Amaran / Bahaya reserved for official water-level threshold states

### FloodGuard derived / predicted

- Label clearly as `FloodGuard prediction` or `FloodGuard-derived`
- Always show that it is not an official JPS warning
- Use outline/subtle derived styling
- Keep prediction timestamps visible

## 12. Responsive behavior

Desktop:
- persistent sidebar
- multi-column card layout

Tablet:
- collapse sidebar
- reduce columns
- keep map/list readable

Mobile:
- sidebar becomes drawer
- single-column content
- cards stack
- tables transform into compact list/cards
- key controls at least 44 px

## 13. Motion

Use only subtle transitions:

```css
transition:
  background-color 160ms ease,
  border-color 160ms ease,
  color 160ms ease,
  transform 160ms ease;
```

Avoid pulsing alarms, looping animations, glowing markers, or decorative motion.

## 14. Global disclaimer

Keep a small persistent footer disclaimer:

> Operational prototype. Not an official warning service.


---

# FloodGuard Penang — Station Detail Page

**Route:** `/stations/:stationId`

## 1. Purpose

Provide the complete operational view for one selected monitoring station.

## 2. Identity header

Breadcrumb:

`Stations > Station Detail`

Show:

- full station name
- district
- sensor type
- source/official station label
- last updated
- Refresh
- All Stations navigation

## 3. Top content row

### Station location — 5 columns

Split panel:

Left:
- map snippet with station marker

Right:
- official current state
- current water level
- latest observation time
- freshness
- station location metadata when available

### Current observation (JPS) — 4 columns

Observed metrics:

- Water level
- Rainfall (1-hour) if supported

Include:

- current value
- delta vs previous observation/hour
- observation time
- retrieved time
- source

### Official JPS thresholds — 3 columns

Definition list:

- Normal
- Waspada
- Amaran
- Bahaya

Use exact thresholds from backend/API.

## 4. FloodGuard predictions

Full-width horizontal section.

Header:

`FloodGuard predictions`

Inline note:

`Not official warnings.`

Use three compact horizon cells:

- 30 minutes
- 60 minutes
- 120 minutes

Each shows:

- forecast value
- change from current
- FloodGuard risk label
- forecast time

Do not use oversized cards.

## 5. Bottom analytics area

### Left main area

#### Water level (JPS)

Line chart with:

- observed water level
- official thresholds
- prediction/forecast section after current observation if available
- range selector

#### Rainfall (JPS)

Bar chart with:

- observed interval rainfall
- range selector
- explicit missing-data gaps

### Right rail

#### Model contributors

Short list of plain-language model factors.

Always state they explain the model, not causal proof.

#### Data quality

Show:

- current status
- latency/freshness
- last received
- missing periods

#### Station metadata

Show supported metadata only.

## 6. Visual hierarchy

Observed JPS data must be visually stronger and more authoritative than FloodGuard predictions.
