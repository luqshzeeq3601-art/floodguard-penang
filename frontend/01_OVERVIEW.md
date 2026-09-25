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

# FloodGuard Penang — Overview Page

**Route:** `/`  
**Reference:** latest generated FloodGuard Overview mockup.

## 1. Purpose

Provide a five-second operational summary of flood conditions across Penang.

## 2. Page header

Left:

- `Overview`
- subtitle: `Real-time flood monitoring for Penang`

Right:

- `Last updated 26 May 2026, 10:15 AM (MYT)`
- `Refresh`
- district selector

## 3. Main layout

Desktop uses a 12-column grid.

### Top row

#### A. Current flood situation hero — 7 columns

Large feature panel with:

- Penang environmental / city image or verified map visual
- location label
- current date/time
- `Highest JPS state in Penang`
- current official state chip
- water-level stations reporting
- rainfall stations reporting
- last updated time

Use a dark readable overlay over the image.

#### B. Current overview — 5 columns

Use a soft card grid containing:

- Water-level stations reporting
- Rainfall stations reporting
- At or above Waspada
- Not reporting
- Active FloodGuard alerts

Cards should be compact, not oversized KPI blocks.

## 4. Middle section

### Needs attention — 6 columns

Use a compact ranked table/list.

Columns:

- rank
- station
- district
- observed value
- official state
- updated time

Tabs:

- All
- Bahaya
- Amaran
- Waspada

Sort by severity, then freshness.

### Penang monitoring map — 4 columns

Map with:

- water-level markers
- rainfall markers
- shared markers
- selected marker popover
- zoom controls
- simple legend

### Operational rail — 2 columns

Stack three small panels:

#### Freshness snapshot

- water-level reporting
- rainfall reporting
- compact progress bars

#### Observed vs FloodGuard

Clearly distinguish:

- JPS observed
- FloodGuard derived

#### Operational highlights

3–4 concise current facts.

#### Official JPS thresholds

Small legend for:

- Normal
- Waspada
- Amaran
- Bahaya

## 5. Bottom section

### Recent alerts

Full-width compact table.

Columns:

- Time (MYT)
- Type
- Station
- District
- Message

Include `View all`.

## 6. Visual emphasis

Priority order:

1. current official flood situation
2. needs attention
3. map
4. active alerts
5. freshness / supporting information

## 7. Do not add

- trend charts
- model-development information
- SHAP plots
- generic KPI decorations
- social/profile widgets
