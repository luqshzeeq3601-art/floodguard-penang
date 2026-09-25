# FloodGuard Penang — Frontend Design System

Status: **Specification** (no React code exists yet; Phase 11 in `TASKS.md`).
Scope: the React/TypeScript operational frontend (`frontend/`, per `docs/14_FOLDER_STRUCTURE.md`).
Not in scope: the Streamlit internal workspace (`docs/08_STREAMLIT_PLAN.md`).

Sources this spec is grounded in: `AGENTS.md`, `docs/02_ARCHITECTURE.md`, `docs/03_DATA_PLAN.md`,
`docs/09_FRONTEND_PLAN.md`, `docs/11_SECURITY_RELIABILITY.md`, `docs/18_ALERTING_PLAN.md`,
ADR-0007/0008/0009, `data/metadata/jps/README.md`, `data/metadata/jps/HISTORICAL_AVAILABILITY.md`,
`scripts/_jps_common.py`.

Every view in this document is gated on the API actually providing its data. Where a capability is
not yet built or verified, the spec marks it **[depends: …]**. Do not render placeholders, sample
numbers, or mock widgets in production for a gated capability — omit it.

---

## 1. Design Goals

1. **Answer "is anything wrong right now, and where?" in under five seconds.** Current official
   threshold state, data freshness and FloodGuard risk must be scannable without clicking.
2. **Never confuse sources.** Observed JPS values, official JPS thresholds, FloodGuard-derived
   statuses and FloodGuard ML predictions must always be distinguishable by label *and* visual
   treatment.
3. **Never hide age or absence.** Every live value carries its observation time or freshness. A
   missing reading is shown as missing, never as zero.
4. **Calm by default.** Normal conditions look quiet. Warning colour appears only where an actual
   condition justifies it.
5. **Dense, not crowded.** Tables and maps over card grids; tight but consistent spacing; tabular
   numerals.
6. **Accessible and resilient.** WCAG 2.2 AA; usable by keyboard, on a phone, and when the API or
   upstream source is degraded.

## 2. Product and User Context

**Product.** An ML flood early-warning platform for Pulau Pinang. It ingests JPS Public Infobanjir
rainfall and water-level observations, derives freshness/quality, and (from Phase 5+) produces
flood-risk predictions at +30, +60 and +120 minutes and water-level forecasts where data supports it.
FloodGuard is **not** an official warning authority (`docs/18_ALERTING_PLAN.md` §6).

**Users of the React app** (`README.md`, ADR-0008):

| User | Primary need | Typical device |
|---|---|---|
| Operations / monitoring user | Scan current station state, spot stale sensors, see predictions and alerts | Desktop 1440–1920 px, often on a wall or second screen |
| Public / community viewer | Understand conditions near a place without being misled | Mobile 360–430 px |
| Portfolio reviewer | Judge engineering and product quality | Laptop |

ML engineers and analysts use Streamlit for EDA, SHAP research, model comparison, drift and
experiment tracking. The React app does not reproduce those pages.

**Verified data facts that shape the UI** (as of 2026-09-24):

| Fact | UI consequence |
|---|---|
| 56 rainfall and 22 water-level JPS records in Pulau Pinang, in 5 districts | Lists are small enough for full tables without pagination by default. |
| JPS listings contain **no coordinates** | The map is blocked until the station master adds verified locations **[depends: station master, Phase 1]**. Every map view must have a list/table equivalent regardless. |
| `jps_internal_id` keys a *site-internal graph link*; 13 IDs appear in both inventories; colocation is unconfirmed | Show one row per sensor record unless the station master explicitly declares a shared site. Never use the internal ID as the display name. |
| `jps_display_station_id` ("ID Stesen") is non-unique and sometimes "No Data" or blank | Show it only as secondary metadata; render bad values as "—". |
| Water-level stations publish four thresholds: Normal, Waspada, Amaran, Bahaya (m) | Official state per water-level station. "Normal" semantics are undocumented (often `0.00`). |
| Rainfall listings publish no thresholds and no status | Rainfall has **no official severity state** in the UI. Do not invent rainfall severity bands. |
| Rainfall listing values: latest 1 h, since midnight, recent daily totals (mm) | These are the observed rainfall figures to show. |
| Source timestamps carry **no timezone**; FloodGuard assumes Asia/Kuala_Lumpur | Label times "MYT" and disclose the assumption (§28). |
| Freshness statuses `FRESH / DELAYED / STALE / NO_DATA / INVALID` are FloodGuard-derived (`scripts/_jps_common.py`; fresh ≤ 30 min, stale > 180 min, provisional) | Present them as FloodGuard freshness, visually unlike JPS threshold states. |
| Missing values arrive as `-9999`, absent rows, or `ERROR` severity | Charts break lines at gaps; `-9999` is never plotted (§22). |
| Ingestion is polling-based (ADR-0009) | The UI polls the API; no "real-time" streaming claims. |

## 3. Design Principles

1. **Source first.** Every value answers *who says so*: JPS (observed/official) or FloodGuard
   (derived/predicted).
2. **Time is part of the value.** A number without its time is incomplete.
3. **Absence is information.** "No reading available" is a first-class state with its own styling.
4. **Colour reinforces, never carries alone.** Severity = colour + icon + text.
5. **The quietest possible normal.** Neutral surfaces; status colour only on the status element,
   not whole rows, panels or pages.
6. **Tables for comparison, maps for geography, charts for time.** Use each only for its job.
7. **The frontend renders; the API decides.** The browser does not compute threshold states,
   freshness, features or risk (`docs/09_FRONTEND_PLAN.md` §4).
8. **No invented capability.** If the API does not return it, it is not on screen.

## 4. Light Theme

Light theme only. There is no dark theme and no theme toggle in scope.

- Application background: off-white `--color-bg` (#F6F8FB).
- Content surfaces (panels, tables, map frame): white `--color-surface`, 1 px `--color-border`.
- Layering is expressed with background tone and borders, not shadows. Shadows exist only for
  overlays that float over content (popovers, dropdowns, drawers, dialogs, toasts).
- Status colour is applied to small elements (chips, markers, icons, a 3 px row accent) — never
  as a full panel or page background, except the Bahaya-level page banner (§25).
- **Danger red must not dominate normal screens.** On a normal day the only saturated colours
  visible are primary blue (interactive), telemetry cyan (data), and green dots.
- Maps use a light, low-saturation vector basemap so markers carry the colour.

## 5. Typography

### Families

| Token | Stack | Use |
|---|---|---|
| `--font-sans` | `"Inter", "Geist", -apple-system, "SF Pro Text", "Segoe UI", Roboto, sans-serif` | All UI text |
| `--font-mono` | `"JetBrains Mono", "Geist Mono", ui-monospace, "SF Mono", Consolas, monospace` | Model version strings, IDs in metadata panels only |

Load Inter (variable, weights 400–600) self-hosted or via Google Fonts with `font-display: swap`.
Enable `font-feature-settings: "cv11", "ss01"` optional; **always** enable tabular numerals on
numeric content: `font-variant-numeric: tabular-nums` (utility class `.num`).

Use `.num` for: water levels, rainfall, thresholds, probabilities, percentages, counts, timestamps,
durations, table numeric columns, axis ticks, chart tooltips.

### Weights

400 regular (body), 500 medium (labels, table headers, buttons, emphasised values), 600 semibold
(page titles, section headings, key measurements). No 700+ weights; no light/thin weights.

### Scale

Base UI size is 14 px (dense operational app). Line heights are multiples of 4.

| Token | Size / line-height | Weight | Letter-spacing | Use |
|---|---|---|---|---|
| `text-2xs` | 11 / 16 | 500 | +0.01em | Map cluster counts, chart axis ticks only (never body copy) |
| `text-xs` | 12 / 16 | 400–500 | 0 | Metadata, timestamps under values, captions, chip text, table secondary line, legend |
| `text-sm` | 13 / 20 | 400–500 | 0 | Table cells, form labels, helper text, tooltips, nav labels |
| `text-base` | 14 / 20 | 400 | 0 | Body text, buttons, inputs, alert row text, panel content |
| `text-md` | 16 / 24 | 500–600 | -0.005em | Panel / card titles, dialog titles, station name in map panel |
| `text-lg` | 18 / 28 | 600 | -0.01em | Section headings (h2) |
| `text-xl` | 20 / 28 | 600 | -0.01em | Station name on Station Detail (h1 on mobile) |
| `text-2xl` | 24 / 32 | 600 | -0.015em | Page title (h1) on desktop/tablet |
| `text-metric` | 28 / 32 | 600 | -0.02em | Current measured value on Station Detail; summary strip numbers |

Rules:

- One `h1` per page. Page title is `text-2xl` (24 px), mobile `text-xl` (20 px). No text larger
  than 28 px anywhere.
- Section headings (`h2`) `text-lg`; panel titles (`h3`) `text-md`. Do not skip levels.
- Units are set in the same size as the value but `--color-text-secondary` and weight 400,
  separated by a thin space: `5.20 m`, `12.5 mm`.
- Alert text: `text-base` 500 for the headline, `text-sm` for context.
- Buttons: `text-base` 500 (`text-sm` 500 for small buttons).
- Map labels: `text-xs` 500 with a 2 px white text halo; show only on hover/selection or at high zoom.
- Sentence case everywhere. Uppercase is reserved for status codes shown verbatim in technical
  context (e.g. a tooltip quoting source severity `ERROR`); never for headings.
- Max line length for prose (help text, empty states): 72 ch.

## 6. Color Tokens

Palette refined from the brief for WCAG contrast (ratios measured against white / `#F6F8FB`).
Each status has a **solid** (fills, markers, icons, lines — non-text, ≥ 3:1), a **text** shade
(≥ 4.5:1 for normal text) and a **subtle** background tint.

### Neutrals

| Token | Value | Contrast on white | Use |
|---|---|---|---|
| `--color-bg` | `#F6F8FB` | — | App background |
| `--color-surface` | `#FFFFFF` | — | Panels, tables, map frame, sidebar |
| `--color-surface-subtle` | `#F9FAFB` | — | Table header, toolbar, inset areas |
| `--color-surface-sunken` | `#F2F4F7` | — | Future (prediction) region in charts, skeletons, disabled input bg |
| `--color-surface-elevated` | `#FFFFFF` | — | Popover, dropdown, dialog (with shadow) |
| `--color-border` | `#E4E7EC` | 1.24 | Panel and table dividers (decorative) |
| `--color-border-strong` | `#8A94A6` | 3.06 | Input/control boundaries, checkbox outlines (must meet 3:1) |
| `--color-text-primary` | `#172033` | 16.3 | Headings, values, body |
| `--color-text-secondary` | `#475467` | 7.7 | Labels, units, metadata |
| `--color-text-tertiary` | `#667085` | 5.0 | Timestamps, captions, placeholder, "—" |
| `--color-text-disabled` | `#98A2B3` | 2.6 | Disabled control text only (exempt) |
| `--color-text-inverse` | `#FFFFFF` | — | Text on primary/danger fills |

The brief's `#667085` secondary text is kept but moved to *tertiary*; secondary is darkened to
`#475467` so labels stay clearly legible on `--color-bg`.

### Interaction

| Token | Value | Use |
|---|---|---|
| `--color-primary` | `#2563EB` (5.2:1) | Primary buttons, links, active nav indicator, selected state |
| `--color-primary-hover` | `#1D4ED8` | Hover/pressed primary |
| `--color-primary-subtle` | `#EFF6FF` | Selected row/nav background |
| `--color-primary-border` | `#BFDBFE` | Selected row border, selected chip border |
| `--color-hover` | `#F2F4F7` | Hover background for rows, nav items, ghost buttons |
| `--color-focus-ring` | `#2563EB` | 2 px focus outline, 2 px offset |
| `--color-disabled-bg` | `#F2F4F7` | Disabled controls |

### Telemetry (observed data)

| Token | Value | Use |
|---|---|---|
| `--color-telemetry` | `#0891B2` | Rainfall markers, rainfall bars, data icons (non-text) |
| `--color-telemetry-text` | `#0E7490` (5.4:1) | Telemetry text |
| `--color-telemetry-subtle` | `#ECFEFF` | Telemetry tint (sparingly) |

### Official JPS threshold states (water level only)

| State | Token prefix | Solid | Text | Subtle bg | Icon (Lucide) |
|---|---|---|---|---|---|
| Normal (below Waspada) | `--color-normal` | `#16A34A` | `#15803D` | `#F0FDF4` | `circle-check` |
| Waspada (alert) | `--color-caution` | `#F59E0B` | `#B45309` | `#FFFBEB` | `circle-alert` |
| Amaran (warning) | `--color-warning` | `#EA580C` | `#C2410C` | `#FFF7ED` | `triangle-alert` |
| Bahaya (danger) | `--color-danger` | `#DC2626` | `#B91C1C` | `#FEF2F2` | `octagon-alert` |

- Amber solid (`#F59E0B`) is 2.2:1 on white: use it for fills with **dark text** (`#172033`, 7.6:1),
  never as a text colour. Orange/red fills use white text only on `#C2410C` / `#DC2626`.
- Amber vs orange vs red are hard to separate for colour-blind users: the icon and the Malay
  label are mandatory on every threshold chip and in the map legend.
- `--color-danger` is also the destructive-action colour. There are no destructive actions in
  current scope.
- Status colours are reserved for status. Never use them for decoration, categories, or charts of
  unrelated series.

### FloodGuard-derived (freshness, predictions)

| Token | Value | Use |
|---|---|---|
| `--color-derived` | `#475467` | Freshness glyphs and chip text (monochrome by design) |
| `--color-prediction` | `#344054` | Prediction/forecast lines, prediction chip border |
| `--color-prediction-band` | `rgba(52, 64, 84, 0.10)` | Forecast interval band (only if API returns an interval) |

Predicted risk *level* reuses the severity hues in an **outline** treatment (§19), so a FloodGuard
risk is never rendered as the solid-tint chip used for official JPS states.

### Charts and map

| Token | Value | Use |
|---|---|---|
| `--chart-grid` | `#EEF0F3` | Gridlines |
| `--chart-axis` | `#8A94A6` | Axis lines/ticks |
| `--chart-rainfall` | `#0891B2` (bars, 80% opacity) | Rainfall interval totals |
| `--chart-water-level` | `#1D4ED8` | Observed water level line |
| `--chart-prediction` | `#344054`, dashed `6 4` | FloodGuard forecast line |
| `--chart-threshold-caution` / `-warning` / `-danger` | status solids, dotted `2 3`, 1 px | Waspada/Amaran/Bahaya reference lines |
| `--chart-gap` | `#F2F4F7` + diagonal hatch | Missing-data interval band |
| `--chart-now` | `#667085`, 1 px solid | "Now / last observation" divider |
| `--map-marker-stroke` | `#FFFFFF` 1.5 px | Marker halo on basemap |
| `--map-marker-selected-ring` | `#2563EB` 2 px + white 2 px gap | Selected marker |
| `--map-marker-muted` | `#98A2B3` | Stale / no-data / invalid marker |

## 7. Spacing and Layout

8 px base grid with 4 px half-steps.

| Token | px | Typical use |
|---|---|---|
| `space-0.5` | 2 | Icon-to-text in chips |
| `space-1` | 4 | Tight inline gaps, chip padding-y |
| `space-2` | 8 | Default inline gap, chip padding-x, table cell padding-y (compact) |
| `space-3` | 12 | Table cell padding-x, control padding-x, gap in toolbars |
| `space-4` | 16 | Panel padding (default), gap between related panels, mobile gutter |
| `space-5` | 20 | Panel padding on ≥1440 px |
| `space-6` | 24 | Page gutter (desktop), gap between page sections |
| `space-8` | 32 | Gap between major page regions |
| `space-10` | 40 | Empty-state vertical padding |
| `space-12` | 48 | Rare; large empty states |

### Fixed dimensions

| Token | Value |
|---|---|
| `--sidebar-width` | 232 px expanded; 64 px collapsed (icons + tooltips) |
| `--header-height` | 56 px |
| `--toolbar-height` | 48 px (filters/actions row) |
| `--control-height-sm` / `-md` / `-lg` | 32 / 36 / 40 px (mobile interactive min 44 px hit area) |
| `--table-row-height` | 40 px default, 36 px compact, 48 px two-line |
| `--table-header-height` | 36 px |
| `--map-panel-width` | 360 px (selected-station panel, desktop) |
| `--detail-rail-width` | 320 px (right rail on Station Detail at ≥1440 px) |
| `--content-max-width` | none for data views; 960 px for prose-only pages |

### Page gutters and gaps

| Breakpoint | Page gutter | Section gap | Panel padding |
|---|---|---|---|
| < 640 | 16 | 16 | 16 |
| 640–1023 | 20 | 20 | 16 |
| 1024–1439 | 24 | 24 | 16 |
| ≥ 1440 | 24 | 24 | 20 |

Layout uses a 12-column CSS grid with `gap: var(--space-6)` on desktop. Data views stretch to the
viewport width (no marketing max-width). The map container has zero internal padding; its frame is
the panel border.

## 8. Radius, Borders and Elevation

### Radius

| Token | Value | Use |
|---|---|---|
| `--radius-sm` | 4 px | Chips, checkboxes, tooltips, table row accent |
| `--radius-md` | 6 px | Buttons, inputs, selects, segmented controls |
| `--radius-lg` | 8 px | Panels, tables, map frame, popovers |
| `--radius-xl` | 12 px | Dialogs, drawers (inner edge), mobile bottom sheet top corners |
| `--radius-full` | 9999 px | Only: status dots, map circle markers, avatar-sized elements |

No radius above 12 px on containers. Chips are 4 px, not pills.

### Borders

- `--border-width`: 1 px. Panels, tables, inputs use 1 px.
- Emphasis border: 2 px, only for selected map markers and the focus ring.
- Row severity accent: 3 px left bar on alert rows and Bahaya/Amaran station rows.
- Dividers inside panels: 1 px `--color-border`; do not nest bordered boxes inside bordered boxes
  (use dividers or spacing instead).

### Elevation

| Token | Value | Use |
|---|---|---|
| `--shadow-0` | none | Panels, tables, cards (default) |
| `--shadow-1` | `0 1px 2px rgba(16,24,40,0.06)` | Sticky header after scroll, map controls |
| `--shadow-2` | `0 4px 12px rgba(16,24,40,0.08), 0 1px 3px rgba(16,24,40,0.06)` | Dropdowns, popovers, map station popover, tooltips |
| `--shadow-3` | `0 16px 32px rgba(16,24,40,0.12)` | Dialogs, drawers, mobile bottom sheet |

### Icons

Lucide (outline, `stroke-width: 1.75`). One family only.

| Token | Size | Use |
|---|---|---|
| `--icon-xs` | 12 | Inside chips |
| `--icon-sm` | 16 | Inline with text, table cells, buttons, nav |
| `--icon-md` | 20 | Header actions, empty states in panels, alert row type icon |
| `--icon-lg` | 24 | Full-page empty/error states only |

No icons larger than 24 px. Icons inherit `currentColor`.

### Focus

`outline: 2px solid var(--color-focus-ring); outline-offset: 2px;` via `:focus-visible` on every
interactive element. Inside tables and lists, focus draws an inset 2 px ring. Never remove focus
outlines without a replacement.

## 9. Application Shell

```text
┌────────────┬───────────────────────────────────────────────────────────────┐
│ ◧ FloodGuard│ Page title                     Updated 01:47 MYT · ↻ Refresh │  56px header
│   Penang    ├───────────────────────────────────────────────────────────────┤
│            │ [source/banner area — only when a banner applies]             │
│ ▣ Overview │ ┌───────────────────────────────────────────────────────────┐ │
│ ◎ Live map │ │                                                           │ │
│ ☰ Stations │ │                    page content                           │ │
│ ↗ Predict. │ │                                                           │ │
│ ⚠ Alerts   │ │                                                           │ │
│ ◉ Data     │ └───────────────────────────────────────────────────────────┘ │
│   status   │                                                               │
│────────────│                                                               │
│ JPS data   │                                                               │
│ ● Retrieved│                                                               │
│   01:47    │                                                               │
│ Not an     │                                                               │
│ official   │                                                               │
│ warning svc│                                                               │
└────────────┴───────────────────────────────────────────────────────────────┘
```

**Sidebar** (`<nav aria-label="Main">`, white surface, right border):

- Brand block (56 px, aligned with header): a simple wordmark "FloodGuard Penang" in `text-md`
  600 with a 20 px outline mark. No tagline, no gradient logo.
- Nav list (§10).
- Footer status block (`text-xs`): "JPS data · Retrieved 01:47" with a freshness glyph for the
  most recent successful ingestion **[depends: `/api/v1/monitoring`]**; below it a persistent
  one-line disclaimer: "FloodGuard is not an official warning service." linking to an About/Sources
  section on the Data status page.

**Header** (`<header>`, white, bottom border, sticky):

- Left: breadcrumb (only below top level, e.g. `Stations / Sg. Air Itam di Lorong Batu Lanchang (F2)`)
  and page `h1`.
- Right: "Updated HH:MM MYT" = time the frontend last received data from the API (distinct from
  source observation time), and an icon+label "Refresh" button. No avatar, notification bell,
  search-everything, or theme toggle unless a later requirement justifies them.

**Content** (`<main id="main">`): scrolls with the window. Avoid nested scroll regions except the
map canvas and the map side list (see §13). A "Skip to main content" link precedes the sidebar.

**Global banners** render between header and content, full content width:
source outage, API unreachable, browser offline, and — when any station is at Bahaya — an
official-state banner (§25). Maximum two banners stacked; the rest collapse into "+1 more".

## 10. Navigation

| Order | Label | Route | Lucide icon | Show when |
|---|---|---|---|---|
| 1 | Overview | `/` | `layout-dashboard` | Always |
| 2 | Live map | `/map` | `map` | Station coordinates exist **[depends: station master]** |
| 3 | Stations | `/stations` | `list` | Always |
| — | Station detail | `/stations/:stationId` | — | Reached from lists/map |
| 4 | Predictions | `/predictions` | `chart-spline` | Prediction endpoint live **[depends: Phase 5, 10]** |
| 5 | Alerts | `/alerts` | `bell` | Alert endpoint live **[depends: Phase 11]** |
| 6 | Data status | `/status` | `activity` | Always (health/ready exist first) |

- Active item: `--color-primary-subtle` background, `--color-primary` 2 px left indicator,
  `--color-text-primary` 500 label. Hover: `--color-hover`.
- Alerts item may show a count badge of *active* alerts only (neutral chip; red only if a
  Bahaya-level official alert is active). No badge when zero.
- Nav items are 36 px tall (44 px on touch).
- Hidden-until-available: routes for gated views return a clear "Not available yet" page if visited
  directly, not a 404 and not a mock.
- URL holds shareable state: filters, sort, selected station, chart range
  (`/stations?district=Timur+Laut+Pulau+Pinang&type=water_level&sort=-level`).

## 11. Information Architecture

```text
Overview ─────────────── summary strip · map (or station list) · attention list · recent alerts
Live map ─────────────── map workspace · filters · legend · selected-station panel · list toggle
Stations ─────────────── table · filters · search
  └─ Station detail ──── identity · current observed · JPS thresholds · trend chart
                          · FloodGuard predictions (+30/+60/+120) · model contributors · data quality
Predictions ──────────── current predictions table (station × horizon) · filters
Alerts ───────────────── chronological alert list · type/severity/status filters · alert detail drawer
Data status ──────────── source availability · freshness breakdown · quality issues · service status
                          · sources & disclaimers
```

**API mapping** (planned endpoints, `AGENTS.md` §18):

| View | Endpoints |
|---|---|
| Overview | `/api/v1/stations`, `/api/v1/observations` (latest), `/api/v1/predictions` (latest), `/api/v1/monitoring`, alerts endpoint |
| Live map | `/api/v1/stations` (with geometry), `/api/v1/observations`, `/api/v1/predictions` |
| Stations | `/api/v1/stations`, `/api/v1/observations` (latest) |
| Station detail | `/api/v1/stations/{id}`, `/api/v1/observations?station_id&from&to`, `/api/v1/predictions?station_id` |
| Predictions | `/api/v1/predictions`, `/api/v1/model` |
| Alerts | alerts endpoint (not yet named in `AGENTS.md`) |
| Data status | `/health`, `/ready`, `/api/v1/monitoring`, `/api/v1/model` |

Explicitly **not** in the React app: experiment tracking, MLflow run browsing, full SHAP plots,
feature inspection, drift reports, model comparison, raw payloads — those are Streamlit.

## 12. Dashboard

Route `/`, title "Overview". Job: tell an operator the current Penang state and where to look.

```text
Desktop ≥1440
┌───────────────────────────────────────────────────────────────────────────────┐
│ Summary strip (one bordered panel, 4–6 cells, dividers between)              │
│ Water-level stations │ At or above Waspada │ Rainfall stations │ Not reporting │ Active FG alerts │
│ 21 of 22 reporting   │ 1 · Amaran          │ 52 of 56 reporting │ 5 stale/no data│ 2              │
├─────────────────────────────────────────────────┬─────────────────────────────┤
│                                                 │ Needs attention      (8)    │
│              Penang map (7–8 cols)              │ ─────────────────────────── │
│   water-level squares, rainfall circles         │ ▲ Sg. X      Amaran  5.61 m │
│                                                 │   Obs 01:45 · Fresh         │
│                                                 │ ◌ Sg. Kerian…  Stale 10 h   │
│  [legend]                         [+][−][⌖]     │ …                           │
│                                                 │ View all stations →         │
├─────────────────────────────────────────────────┴─────────────────────────────┤
│ Recent alerts (last 24 h, max 5 rows)                        View all alerts →│
└───────────────────────────────────────────────────────────────────────────────┘
```

**Summary strip** — a single panel with divided cells, not separate cards. Each cell: label
(`text-sm` secondary), value (`text-metric`, `.num`), one supporting line (`text-xs`). Cells:

| Cell | Value | Source | Show when |
|---|---|---|---|
| Water-level stations | "21 of 22 reporting" (reporting = Fresh or Delayed) | observations + freshness | Always |
| At or above Waspada | Count + highest official state chip | API official threshold state | Always for WL; value "None" when zero (neutral) |
| Rainfall stations | "52 of 56 reporting" | observations + freshness | Always |
| Not reporting | Count of Stale + No data + Invalid, both types | freshness | Always |
| Highest 1 h rainfall | Value in mm + station name + obs time | observations | Optional; only if it helps operators — keep off by default |
| Active FloodGuard alerts | Count; labelled "FloodGuard" | alerts | **[depends: alerts]** |

No percentages-as-decoration, no trend arrows without a defined comparison, no donuts, no gauges.

**Map** — dominant region (`col-span-8` at ≥1440, `col-span-7` at 1024–1439), min-height
`calc(100vh - header - strip - 48px)`, clamp 420–720 px. Same marker system as Live map (§23).
Clicking a marker selects it and highlights the matching row in the attention list; "Open station"
navigates to Station Detail. **Until coordinates exist**, this region is replaced by a district-grouped
station table (same columns as §14, compact) — not by a blank map or a fake one.

**Needs attention list** — ordered: Bahaya → Amaran → Waspada (official), then FloodGuard high-risk
predictions **[depends]**, then Stale/No data/Invalid. Each row: severity/freshness glyph, station
name (truncate with tooltip), state chip, value with unit, `Obs HH:MM` + freshness. Empty state:
"All reporting stations are below Waspada and reporting on time." (only when true — requires full
data).

**Recent alerts** — compact alert rows (§20), last 24 h, max 5. **[depends: alerts]**; omit when unavailable.

**Trend charts on the dashboard**: none by default. Trends live on Station Detail, where the context
(thresholds, gaps) is present.

## 13. Live Map

Route `/map`. Job: geographic scan and station selection. **[depends: verified coordinates in the
station master]**.

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│ Toolbar: [Sensor type ▾] [District ▾] [Freshness ▾] [Official state ▾] [FG risk ▾]│  [Map | List]
├──────────────────────────────────────────────────────────────┬────────────────┤
│                                                              │ Selected panel │
│                                                              │ (360 px)       │
│                           MAP                                │                │
│                                                              │ Sg. Air Itam…  │
│                                                              │ Timur Laut ·   │
│  ┌ Legend ─────────┐                                         │ Sg. Pinang     │
│  │ ■ Water level   │                                  [+]    │── Observed ─── │
│  │ ● Rainfall      │                                  [−]    │ 5.00 m  01:45  │
│  │ state · fresh…  │                                  [⌖]    │ Fresh          │
│  └─────────────────┘                                         │── JPS ─────────│
│                                                              │ thresholds     │
│                                                              │── FloodGuard ──│
│                                                              │ +30/+60/+120   │
│                                                              │ [Open station] │
└──────────────────────────────────────────────────────────────┴────────────────┘
```

- Map fills the content area height (`100vh - header - toolbar - gutter`); the page itself does
  not scroll on desktop. The selected panel scrolls internally if needed.
- **Filters** appear only for dimensions the API provides: sensor type (Rainfall / Water level),
  district (5 official district names, verbatim), freshness (Fresh / Delayed / Stale / No data /
  Invalid), official state (Normal / Waspada / Amaran / Bahaya; water level only), FloodGuard risk
  **[depends]**. Active filters show as removable chips below the toolbar with "Clear all".
- **Selected-station panel** (right side, 360 px; does not cover the map on ≥1024 px — the map
  resizes). Sections in fixed order, each with a source label:
  1. Identity: station name (`text-md` 600), district · basin/sub-basin (WL), sensor type(s).
  2. **Observed** (source: JPS): current value(s), `Obs 24 Sep 01:45 MYT`, freshness chip.
     Rainfall: "1 h rainfall", "Since midnight". Water level: "Water level".
  3. **JPS thresholds** (water level only): official state chip + compact threshold list
     (Waspada / Amaran / Bahaya values, m). "Normal" shown as published with a tooltip noting its
     meaning is not documented by JPS.
  4. **FloodGuard prediction** **[depends]**: compact 3-row horizon table (§15 structure).
  5. Primary action: "Open station" (button). Secondary: close (icon button, `aria-label="Close station panel"`).
- The Observed/JPS block and the FloodGuard block are separated by a divider and distinct section
  headings; the FloodGuard block uses the prediction treatment (§19). They are never merged into
  one list of numbers.
- **Map | List toggle** (segmented control) switches the workspace to the Stations table with the
  current filters applied. This is the accessible alternative and the default on screen readers'
  skip link "Skip map, go to station list".

## 14. Stations

Route `/stations`. Job: find and compare stations. A table, not a card grid.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ [Search station name]  [Type: All|Water level|Rainfall] [District ▾] [Freshness ▾]  56+22 │
├───────────────────────────┬──────────────┬────────┬──────────────┬───────────┬──────────┤
│ Station ↑                 │ District     │ Type   │ Latest value │ Official  │ Last obs │
│                           │              │        │              │ state     │          │
├───────────────────────────┼──────────────┼────────┼──────────────┼───────────┼──────────┤
│ Sg. Air Itam di Lorong …  │ Timur Laut … │ ■ WL   │ 5.00 m       │ ◉ Normal  │ 01:45    │
│ Sungai Pinang · Sg. Air…  │              │        │              │           │ ● Fresh  │
│ Kolam Bersih              │ Timur Laut … │ ● RF   │ 0.0 mm (1 h) │ —         │ 01:30    │
│                           │              │        │ 3.5 mm today │           │ ● Fresh  │
│ Sg. Kerian di Sri Sangl…  │ S. P. Selatan│ ■ WL   │ —            │ —         │ 23 Sep   │
│ Sungai Kerian · Sg. Ker…  │              │        │ No reading   │           │ ○ Stale  │
└───────────────────────────┴──────────────┴────────┴──────────────┴───────────┴──────────┘
```

Columns (desktop):

| Column | Content | Sort | Notes |
|---|---|---|---|
| Station | Name (verbatim JPS name, `text-sm` 500); second line basin · sub-basin (WL) in `text-xs` tertiary | A–Z | Link to Station Detail. Never show `jps_internal_id` here. |
| District | Official district name | A–Z | Filterable |
| Type | Glyph + "Water level" / "Rainfall" (abbreviate "WL"/"RF" only < 1280 px with `title`) | — | Shared site: "Water level + rainfall" only when station master declares it |
| Latest value | WL: `5.00 m`. RF: `x.x mm` 1 h, second line `since midnight` total | Numeric | Right-aligned, `.num`. "—" + "No reading" when absent |
| Official state | JPS threshold chip (WL) / "—" (RF, no official state exists) | Severity | |
| FloodGuard risk | Highest risk across horizons with horizon, outline chip | Severity | **[depends]**; column hidden until available |
| Last observation | `HH:MM` if today else `DD Mon HH:MM`; second line freshness chip | Time | `title` shows full ISO time + "MYT (assumed)" |

- Default sort: official state (worst first), then freshness (worst first), then name.
- Row height 48 px (two-line). Numeric columns right-aligned; text left-aligned.
- Search matches station name, district and basin; also matches `jps_display_station_id` quietly.
- Row click and Enter open Station Detail. Rows are links, not click-handlers on `<tr>` alone
  (put a real `<a>` in the Station cell and make the row's hover a visual extension).
- Header count: "22 water-level · 56 rainfall" (from API), updated with filters: "Showing 9 of 78".
- **Shared monitoring sites**: until the station master confirms colocation, list each sensor record
  separately. When confirmed, one row with both values stacked and Type "Water level + rainfall".
  Never merge by matching `jps_internal_id` in the browser.
- States: hover `--color-hover`; selected (e.g. from map) `--color-primary-subtle` + 2 px left
  primary bar; keyboard focus inset ring; loading = 8 skeleton rows; empty (filters) = "No stations
  match these filters." + "Clear filters"; stale rows keep full contrast (do not grey out a whole row
  — the freshness chip carries it); API error = inline error panel replacing the table body with
  retry.
- No pagination by default (≤ ~100 rows). Sticky header. If the station set grows beyond 200,
  add pagination (§21).

## 15. Station Detail

Route `/stations/:stationId`. Job: understand one station now and over the last hours, then see
what FloodGuard predicts.

```text
Desktop ≥1440
┌───────────────────────────────────────────────────────────────────────────────┐
│ Stations / Sg. Air Itam di Lorong Batu Lanchang (F2)                          │
│ Sg. Air Itam di Lorong Batu Lanchang (F2)                  [Water level] [RF] │
│ Timur Laut Pulau Pinang · Sungai Pinang › Sg. Air Itam · JPS ID 1910131WL     │
├────────────────────────────── Observed · JPS ─────────────┬───────────────────┤
│ Water level          │ 1 h rainfall     │ Since midnight   │ JPS thresholds    │
│ 5.00 m  ◉ Normal     │ 0.0 mm           │ 3.5 mm           │ Waspada   5.20 m  │
│ Obs 01:45 MYT · Fresh│ Obs 01:45 · Fresh│                  │ Amaran    5.50 m  │
│ 0.20 m below Waspada │                  │                  │ Bahaya    6.00 m  │
├──────────────────────────────────────────────────────────┤ Normal 4.00 (i)   │
│ Recent observations           [6 h | 24 h | 3 d | 7 d]    │                   │
│ ┌─────────────────────────────────────────────┬─────────┐ │ Data quality      │
│ │ ── water level (obs)  ···· Bahaya/Amaran    │ ‑ ‑ fcst│ │ Freshness: Fresh  │
│ │ ▮▮ rainfall (mm/interval)   ░ no data       │   Now │ │ │ Gaps (24 h): 1    │
│ └─────────────────────────────────────────────┴─────────┘ │ Last retrieved    │
├──────────────────────── FloodGuard prediction ────────────┤ 01:47             │
│ Horizon │ Flood-risk prob. │ Risk (FG)   │ Forecast level │                   │
│ +30 min │ 12%  ▂          │ ◇ Low       │ 5.04 m         │                   │
│ +60 min │ 18%  ▃          │ ◇ Low       │ 5.09 m         │                   │
│ +120 min│ 31%  ▅          │ ◇ Elevated  │ 5.18 m         │                   │
│ Based on obs 01:45 · generated 01:47 · model v… · input quality: valid       │
│ Model contributors (+60 min): recent 1 h rainfall ↑, water-level rise (30 min)↑│
└───────────────────────────────────────────────────────────┴───────────────────┘
```

(Values in sketches are illustrative layout text only; the implementation renders API data.)

Hierarchy, top to bottom:

1. **Identity header**: station name (`h1`, `text-2xl`), sensor-type chips, context line:
   district · main basin › sub-basin (WL) · "JPS ID" (display ID, if `ok`) in `text-xs` tertiary.
   Source attribution link "Source: JPS Public Infobanjir". Internal IDs only in a collapsed
   "Technical details" disclosure at the bottom (mono font).
2. **Observed · JPS** section: one measurement block per sensor. Value in `text-metric`, unit,
   official state chip (WL), `Obs <date time> MYT`, freshness chip. For WL, a plain-language
   distance line computed **by the API**: "0.20 m below Waspada" / "0.11 m above Amaran".
3. **JPS thresholds** (right rail ≥1440; below measurements otherwise): a two-column definition
   list — Malay term with English gloss in tooltip ("Waspada — alert level"), value in m, `.num`,
   right-aligned. "Normal" listed last with an info tooltip: "Published by JPS; its meaning is not
   documented." Show `fg_threshold_order_flag` problems as an inline caution note.
4. **Recent observations chart** (§22): range segmented control 6 h / 24 h / 3 d / 7 d (limited to
   what the API serves). Water level line + threshold reference lines; rainfall as bars on a
   separate lower panel sharing the time axis (never a dual y-axis on one plot). If the station has
   a forecast, the forecast segment appears right of a "Now" divider on a `--color-surface-sunken`
   background, dashed, labelled "FloodGuard forecast".
5. **FloodGuard prediction** section **[depends]**: heading "FloodGuard prediction" with a source
   note "Model output — not an official JPS warning." Compact horizon table (not three cards):
   Horizon · Flood-risk probability (number + 48 px bar) · Risk (FG outline chip) · Forecast water
   level (if supported). Footer line: based-on observation time, generated time, model version,
   input quality.
6. **Model contributors** **[depends: per-prediction factors in the API]**: at most 3–5 factors for
   one selected horizon, as a list: factor name in plain language, direction (increases/decreases
   predicted risk), optional relative bar. Heading "Model contributors", note: "Factors that most
   influenced this prediction. They describe the model, not the cause of flooding." No SHAP
   waterfall/beeswarm plots, no raw feature names (map `rainfall_1h` → "Rainfall, last 1 h").
7. **Data quality** (rail): current freshness with rule tooltip ("FloodGuard-derived: fresh when the
   observation is ≤ 30 min old; stale after 180 min"), count of gaps in the displayed range, last
   retrieved time, any quality flags from the API in plain language.
8. **Technical details** (collapsed): FloodGuard station ID, JPS internal ID, display ID, source URL.

Rainfall-only station: sections 1, 2, 4 (rainfall bars only), 7, 8. Omit the thresholds section
entirely (JPS publishes none for rainfall). Show the prediction section only if the model covers
rainfall-only stations **[depends]**.

## 16. Predictions

Route `/predictions`. Job: see current FloodGuard predictions across stations, with their inputs'
quality. **[depends: live inference + prediction persistence, Phases 5, 10]**. Not a model-dev tool.

```text
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ Note: FloodGuard predictions are model outputs, not official JPS warnings. Model v… ⓘ │
│ [Horizon: All|+30|+60|+120] [District ▾] [Risk ▾] [Input quality ▾]                   │
├──────────────────────┬──────────┬──────────┬──────────┬──────────┬──────────┬─────────┤
│ Station              │ +30 min  │ +60 min  │ +120 min │ Based on │ Generated│ Input   │
│                      │ prob·risk│ prob·risk│ prob·risk│ obs      │          │ quality │
├──────────────────────┼──────────┼──────────┼──────────┼──────────┼──────────┼─────────┤
│ Sg. X                │ 12% Low  │ 18% Low  │ 31% Elev.│ 01:45    │ 01:47    │ Valid   │
│ Sg. Y                │ ⚠ Based on delayed data (55 min)                     │ Delayed │
│                      │ 40% …    │ …        │ …        │ 00:55    │ 01:47    │         │
│ Sg. Kerian …         │ Prediction unavailable — input data stale (last 15:15, 23 Sep)│
└──────────────────────┴──────────┴──────────┴──────────┴──────────┴──────────┴─────────┘
```

- One row per station; horizon cells show probability (`.num`, integer %) above an FG outline risk
  chip. Forecast water level appears as a third line in each cell when available, or in a
  dedicated "Forecast level" column when the horizon filter selects one horizon.
- The horizon filter set to one horizon turns the table into a sortable single-horizon view:
  Station · Probability · Risk · Forecast level · Based on obs · Generated · Model · Input quality.
- Model version appears once in the page note when all rows share it; as a column only if versions
  differ across rows.
- **Input quality** column uses the freshness chip vocabulary plus API quality labels.
- **Degraded** (prediction made on Delayed input): row keeps values, adds a caution-text line with
  `triangle-alert` 12 px: "Based on delayed data (55 min old)". Values render in
  `--color-text-secondary` rather than primary.
- **Unavailable**: the three horizon cells merge into one cell with `circle-slash` icon and the
  API-supplied reason, e.g. "Prediction unavailable — input data stale", "— model unavailable",
  "— station not covered by the model", "— horizon not supported". Never show a probability for
  stale/invalid input.
- **Uncertainty**: probabilities are labelled "Flood-risk probability" with a tooltip: "Model
  estimate for the horizon. Calibration: <API status>." If the API marks calibration as not
  validated, the page note says so. Forecast intervals shown only if the API returns them.
- No green/red binary: risk is conveyed by label + outline chip + icon; probability numbers stay in
  neutral ink.
- Risk category names come from the API/label design **[depends: Phase 3 label definition]**.
  They must not reuse JPS terms (Waspada/Amaran/Bahaya) and always render with the FloodGuard
  outline treatment.

## 17. Alerts

Route `/alerts`. Job: chronological record of what fired, why, and whether it is still active.
**[depends: alert schema + service, Phases 8, 11]**.

```text
┌───────────────────────────────────────────────────────────────────────────────────┐
│ [Type: All|Official threshold|FloodGuard prediction|Data quality|System] [Status ▾]│
│ [Severity ▾] [District ▾] [Date range]                                            │
├───────────────────────────────────────────────────────────────────────────────────┤
│ Today                                                                             │
│▌▲ Amaran reached · Sg. X                        JPS official    Active   01:45    │
│▌  Water level 5.61 m ≥ Amaran 5.50 m · Obs 01:45 MYT                              │
│ ◇ High predicted risk +60 min · Sg. Y           FloodGuard      Active   01:47    │
│   Probability 81% · based on obs 01:45 · model v…                                 │
│ ◌ Station stale · Sg. Kerian di Sri Sanglang    Data quality    Active   04:15    │
│   No observation since 23 Sep 15:15                                               │
│ Yesterday                                                                         │
│ ⓘ JPS water-level listing unreachable           System          Resolved 22:10    │
└───────────────────────────────────────────────────────────────────────────────────┘
```

Alert types, each with its own label and icon, never collapsed into one channel
(`docs/18_ALERTING_PLAN.md` §1):

| Type | Label | Icon | Severity vocabulary | Visual treatment |
|---|---|---|---|---|
| Official threshold state | "JPS official" | severity icon (§6) | Waspada / Amaran / Bahaya | Solid-tint chip; 3 px left accent in status solid |
| FloodGuard prediction | "FloodGuard" | `chart-spline` | FG risk labels **[depends]** | Outline chip; dashed 3 px left accent (`border-left-style: dashed`) |
| Data quality | "Data quality" | `clock-alert` / `circle-dashed` | Delayed / Stale / No data / Invalid | Monochrome derived chip; no accent colour |
| System | "System" | `server` | Degraded / Unavailable | Neutral chip; no accent colour |

Alert row content: type label, severity chip, headline (`text-base` 500: condition + station),
context line (`text-sm` secondary: value vs threshold, or probability + horizon + based-on time +
model version, or last observation time), status (Active / Resolved — per `docs/09_FRONTEND_PLAN.md`),
created time. Grouped by day with sticky day headers. Newest first.

**Alert detail drawer** (right, 480 px; full-screen sheet on mobile): full payload fields from the
alerting plan — station, observation timestamp, horizon, probability, risk category, forecast level,
model version, input quality, top contributing factors — plus state history (transitions) and
delivery status (Pending / Sent / Failed / Retried, `docs/11_SECURITY_RELIABILITY.md` §7) when
provided. Link to Station Detail.

**No acknowledge/resolve/assign/snooze controls.** The planned backend defines system-driven
Active/Resolved status only. Add controls only when an authenticated operator workflow exists.

FloodGuard alerts never use the words "official", "Waspada", "Amaran" or "Bahaya", and never use
the solid-tint chip style.

## 18. System and Data Status

Route `/status`, title "Data status". Job: tell users whether they can trust what they see.

Sections (each a panel with a small table, not KPI cards):

1. **Sources** — rows: "JPS rainfall listing", "JPS water-level listing" (plus future sources only
   once verified). Columns: status (Available / Degraded / Unavailable, from API), last successful
   retrieval, newest observation time in that retrieval, stations returned (e.g. 56 of 56 expected).
2. **Station freshness** — counts per freshness state per sensor type, each count linking to the
   Stations table pre-filtered. Include the rule text: "Freshness is derived by FloodGuard from the
   observation age: Fresh ≤ 30 min, Delayed ≤ 180 min, Stale > 180 min. Provisional rule." (render
   values from the API/config, not hardcoded strings).
3. **Data quality issues** — current open issues from `/api/v1/monitoring` in plain language
   (e.g. "Threshold values out of order", "Observation time in the future", "Schema change detected
   in source listing"). No raw exceptions, stack traces, SQL, payloads, hostnames or credentials.
4. **Services** — API (from `/health`), Readiness (from `/ready`: ready / not ready with a
   plain-language reason such as "Model not loaded"), Prediction service: model version in use and
   loaded time (from `/api/v1/model`). No MLflow run IDs, artifact URIs or registry internals.
5. **Sources and disclaimers** — data source attribution (JPS Public Infobanjir), the timezone
   assumption, and "FloodGuard is not an official emergency-warning authority. For official flood
   information, refer to JPS and the relevant authorities." Link to the official Public Infobanjir
   site.

## 19. Data Semantics

**Mandatory rule.** Every value belongs to exactly one concept below and uses that concept's label
and treatment everywhere.

| Concept | UI label | Examples | Visual treatment | Required context |
|---|---|---|---|---|
| Observed | "Observed" section heading; value label e.g. "Water level", "1 h rainfall" | 5.00 m, 0.0 mm | Primary ink value, telemetry glyph; charts: solid line / solid bars | Observation time (`Obs 01:45 MYT`) + freshness |
| Official JPS threshold | "JPS thresholds"; state chip "Waspada" etc. | Waspada 5.20 m | Solid-tint chip (subtle bg + status text + icon); chart: dotted reference line with right-edge label | Source attribution "JPS" |
| Official source information | "Source: JPS" | station name, district, basin, display ID | Plain text; attribution line | Source name/link |
| FloodGuard prediction | "FloodGuard prediction", "30 min prediction" | 31% · Elevated (+120 min) | Outline chip (white bg, 1 px status-solid **dashed** border, status text, risk icon); section heading or source label carries "FloodGuard" | Horizon, based-on obs time, generated time, model version, input quality |
| Forecast | "FloodGuard forecast", "Forecast water level" | 5.18 m at +120 min | `--color-prediction` dashed line on sunken "future" background; forecast values in secondary ink, always labelled "Forecast" | Horizon, generated time, model version |
| Derived freshness | "Freshness" (chip text "Fresh", "Delayed", "Stale", "No data", "Invalid time") | Delayed · 55 min | Monochrome chip with glyph: ● fresh, ◐ delayed, ○ stale, ◌ (dashed) no data, ⊘ invalid | Tooltip: "Derived by FloodGuard from observation age" |
| Unavailable / No data | "No reading available", "Prediction unavailable" | — | Em dash "—" in tertiary + reason text; never `0`, never blank | Reason and last known time if any |

Rules:

1. A FloodGuard prediction is never styled, worded, or positioned as an official JPS warning.
   Official states use Malay JPS terms and solid-tint chips; FloodGuard uses its own labels and
   outline chips.
2. Freshness statuses are FloodGuard-derived and monochrome, so they can't be read as JPS
   statuses or as severity. Do not display them in uppercase (the enum values stay in code).
3. Rainfall has no official state. Do not colour rainfall by amount on the map or in tables.
4. Observed and predicted values are never in the same table column or the same chart series.
   On charts they are separated by the "Now" divider, background tone, line style and legend.
5. Every live value shows its observation time or a freshness chip whose tooltip gives the time.
6. `-9999`, `ERROR`-only readings and absent rows are "No reading available", not values.
7. Distances to thresholds, official state and freshness are computed by the API; the browser only
   formats them.

## 20. Components

State vocabulary used below: **default, hover, active (pressed), focus-visible, disabled, loading,
selected, error (validation), unavailable-data**. "n/a" = state does not apply.

### Button

Variants: primary (filled `--color-primary`, white text), secondary (white, `--color-border-strong`
border, primary ink text), ghost (transparent, secondary text), danger (reserved; unused now).
Sizes sm 32 / md 36 / lg 40 px; `--radius-md`; padding-x 12/14/16; icon 16 px with 6 px gap.

| State | Treatment |
|---|---|
| hover | primary → `--color-primary-hover`; secondary/ghost → `--color-hover` bg |
| active | 1 px translate-free; darker bg (`#1E40AF` primary, `#E4E7EC` others) |
| focus-visible | focus ring |
| disabled | `--color-disabled-bg`, `--color-text-disabled`, no pointer; keep `aria-disabled` + tooltip reason where helpful |
| loading | spinner (16 px) replaces icon, label kept ("Refreshing…"), `aria-busy`, width fixed |
| selected | n/a (use segmented control/toggle) |
| error / unavailable | n/a |

Labels are verbs: "Refresh", "Open station", "Clear filters". Important actions always have a
text label; icon-only allowed only for universally understood controls (close, zoom, collapse) and
always have `aria-label` + tooltip.

### Icon button

32/36 px square (44 px hit area on touch), ghost style, `--radius-md`. Same states as Button.
`aria-label` mandatory; tooltip mirrors it.

### Text input / search

36 px, white, 1 px `--color-border-strong`, `--radius-md`, padding-x 12, `text-base`. Label above
(`text-sm` 500) — placeholder is never the label. Search has a leading `search` icon and a clear
button when non-empty.

| State | Treatment |
|---|---|
| hover | border `#667085` |
| focus-visible | border primary + focus ring |
| disabled | `--color-disabled-bg`, disabled text |
| error | border `--color-danger`, helper text in `--color-danger-text` with `circle-alert` 12 px, `aria-invalid`, `aria-describedby` |
| loading | n/a (search results show loading in the table) |

### Select / dropdown / multi-select filter

Trigger identical to input with `chevron-down`. Filter selects show "District: All" / "District: 2
selected". Menu: `--surface-elevated`, `--shadow-2`, `--radius-lg`, items 32 px (44 touch), hover
`--color-hover`, selected = check icon + 500 weight, keyboard: arrow keys, type-ahead, Esc closes and
returns focus. Disabled options show reason in tooltip. Options with zero matches show the count
"(0)" rather than being hidden, so filters don't reshuffle.

### Date / time range control

Used only for Alerts history and chart ranges beyond presets. Presets first (Last 24 h, 3 days,
7 days), then a custom range with two date-time inputs in `DD/MM/YYYY HH:mm` (24 h), MYT label
shown. Validation: end ≥ start; range ≤ API maximum; error text inline. Never allow future end
times for observation queries.

### Tabs

Underline tabs for switching sections within a page (e.g., Station Detail on mobile:
Observed | Predictions | Quality). 40 px, `text-sm` 500; selected = primary text + 2 px underline;
hover = primary-subtle underline; roving tabindex, arrow-key navigation, `role="tablist"`.

### Segmented control

For mutually exclusive view options (Map | List, 6 h | 24 h | 3 d | 7 d, horizon filter). 32 px,
`--radius-md` container with 1 px border, items separated by dividers; selected = white bg +
`--shadow-1` inside `--color-surface-subtle` track, 500 weight, `aria-pressed`/radio semantics.
Unavailable option (e.g., 7 d when API serves less) = disabled with tooltip reason.

### Tooltip

Dark tooltip is avoided in a light theme: white `--surface-elevated`, `--shadow-2`, 1 px border,
`text-sm`, max-width 280 px, 400 ms open delay, instant on focus, Esc dismisses. Never the only
place for essential information (except full timestamps and glossary text).

### Dialog

Rare (no destructive or form-heavy flows). Centered, max-width 480 px, `--radius-xl`, `--shadow-3`,
scrim `rgba(16,24,40,0.40)`, focus trapped, Esc closes, focus returns to trigger.

### Drawer / bottom sheet

Right drawer 480 px (alert detail; mobile filters as left/bottom). Mobile: bottom sheet with drag
handle, 3 snap points (peek 30%, half, full) for the map station panel. Same focus rules as dialog.

### Table and pagination

See §21.

### Metric summary (summary strip cell)

Label `text-sm` secondary · value `text-metric` `.num` · supporting line `text-xs` tertiary.
Cells separated by 1 px dividers inside one panel. Loading = skeleton bar at value size.
Unavailable = "—" + reason ("No data from API"). Not clickable unless it links to a filtered view,
in which case the whole cell is a link with hover `--color-hover` and focus ring.

### Status chip

Height 20 px, `--radius-sm`, padding 2 × 6 px, `text-xs` 500, 12 px icon + label. Types:

| Chip | Background | Border | Text | Icon |
|---|---|---|---|---|
| JPS official state | status subtle | none | status text | severity icon |
| FloodGuard risk | white | 1 px dashed status solid | status text | severity icon (outline) |
| Freshness | white | 1 px `--color-border` | `--color-derived` | freshness glyph |
| Sensor type | `--color-surface-subtle` | none | secondary | `droplets` (rainfall) / `waves` (water level) |
| Neutral / count | `--color-surface-subtle` | none | secondary | none |

Chips are not interactive. Filter chips (removable) are a separate component: 28 px, white,
1 px border, label + `x` icon button with `aria-label="Remove filter: District Timur Laut Pulau Pinang"`.

### Alert row

See §17. 3 px left accent (JPS: solid; FloodGuard: dashed; others: none). Hover `--color-hover`,
focus inset ring, selected (drawer open) `--color-primary-subtle`. Entire row opens the drawer via
a real `<button>` covering the headline.

### Station row

See §14. Two-line, 48 px. Stale/no-data rows keep normal contrast; the "Latest value" cell shows "—".

### Map popover (hover)

Compact tooltip on marker hover/focus: station name, type, value + unit, `Obs HH:MM`, state chip or
freshness chip. `--shadow-2`, max-width 240 px. Click opens the selected panel instead.

### Map legend

Collapsible panel bottom-left, white, `--shadow-1`, `--radius-lg`, `text-xs`. Groups: Sensor type
(shapes), Official state (WL colours with icons + Malay terms + English gloss), Freshness (marker
treatments), Selection. Expanded by default on desktop, collapsed ("Legend") on mobile.

### Charts and chart tooltip

See §22.

### Empty state

In-panel: 20 px icon (tertiary), title `text-md` 500, one-sentence description `text-sm` secondary,
optional single action. Centered, `space-10` vertical padding. No illustrations.

### Skeleton

`--color-surface-sunken` blocks matching final layout sizes, `--radius-sm`. Subtle shimmer 1.2 s
disabled under `prefers-reduced-motion`. `aria-busy="true"` on the container with a visually hidden
"Loading stations".

### Banner

Full-width inside content, 1 px border, `--radius-lg`, icon + title + one sentence + optional action.
Variants: info (primary subtle), caution (caution subtle, for degraded data), danger (Bahaya official
state only), neutral (offline). `role="status"` (info/caution/neutral) or `role="alert"` (danger).
Dismissible only if informational; source-outage and Bahaya banners persist while true.

### Toast

Only for results of user actions (e.g. "Refreshed", "Couldn't refresh — retrying"). Bottom-right,
max 1 visible, 5 s, `role="status"`. Never for flood conditions (those are banners/alerts).

### Error message

Inline where the failure happened: `circle-alert` + "Couldn't load stations." + plain reason
("The FloodGuard API didn't respond.") + "Retry". Include a request/correlation ID only if the API
returns one, in `text-xs` mono. Never show stack traces or raw error objects.

## 21. Tables

- Semantic `<table>` with `<caption>` (visually hidden if redundant), `<thead>`, `scope="col"`;
  sortable headers are `<button>`s inside `<th>` with `aria-sort`.
- Header 36 px, `--color-surface-subtle`, `text-xs` 500 secondary, sentence case, sticky.
- Rows 40 px (single line) / 48 px (two-line); 1 px `--color-border` row dividers; no zebra stripes.
- Cell padding 8 × 12 px. First column left padding 16 px.
- Numbers right-aligned, `.num`, consistent decimals per column (m: 2 dp; mm: 1 dp; % integer).
  Units in header ("Water level (m)") *or* in cells — pick per table; don't do both.
- Text truncation with `…` + `title`/tooltip for station names at < 1280 px; never truncate numbers
  or times.
- Sort indicator: `arrow-up`/`arrow-down` 12 px beside header label; unsorted sortable columns show
  `arrow-up-down` on hover/focus only.
- Row states: hover, selected, focus (inset ring), loading (skeleton rows), empty (in-table empty
  state spanning all columns), error (in-table error state with retry).
- Pagination (only when > 200 rows or for alert history): bottom bar, "1–50 of 312", previous/next
  icon buttons with labels, page size select (25/50/100). Alert history may use "Load older alerts"
  instead of pages.
- Horizontal scroll allowed only inside the table wrapper on narrow screens with the first column
  sticky; below 640 px use the card-list transform (§26).

## 22. Charts

One charting library across the app (recommended: Recharts or Apache ECharts — must support null
gaps, reference lines, dashed series, and custom tooltips).

**Allowed forms**: line (water level, forecast), bars (rainfall per interval), threshold reference
lines, event/alert markers, small multiples sharing a time axis. Area fill only for a forecast
interval band returned by the API. **Not allowed**: 3D, gauges, radar, pie/donut, decorative
gradients, smoothed (`monotone`/spline) curves on observations (use straight segments; smoothing
invents values).

**Encodings (identical everywhere):**

| Series | Mark | Colour | Style | Axis |
|---|---|---|---|---|
| Observed water level | line 2 px, points hidden (shown on hover) | `--chart-water-level` | solid | Left, "Water level (m)" |
| FloodGuard forecast water level | line 2 px | `--chart-prediction` | dashed `6 4`; future region `--color-surface-sunken` | Same axis |
| Forecast interval | band | `--color-prediction-band` | — | Same axis; only if API provides |
| Rainfall | bars, per interval (5 min / hourly as served) | `--chart-rainfall` | solid, 1 px gap | Separate panel below, "Rainfall (mm)" |
| Waspada / Amaran / Bahaya | horizontal line 1 px | status solid | dotted `2 3`; right-edge label "Amaran 5.50 m" | WL axis |
| Now / last observation | vertical line | `--chart-now` | solid 1 px, label "Last obs 01:45" | — |
| Alert event | small marker on x-axis | severity colour + icon shape | — | — |

- Y-axis for water level: auto-range padded to include Waspada at minimum (so the relationship is
  visible) but not forced to 0. Always label units. Rainfall y-axis starts at 0.
- X-axis: time in MYT, 24 h ticks (`01:00`, `02:00`; date labels at midnight `24 Sep`).
  Gridlines horizontal only, `--chart-grid`.
- Legend: always visible above the plot, left-aligned, `text-xs`; entries use the real mark style
  (dashed sample for forecast). Legend includes "No data" swatch when gaps are present.
- **Missing data** (normalized by the API to `null` with a reason):
  - `-9999`, `ERROR` with no valid value, and absent 5-min rows → `null`. Lines **break** at nulls
    (`connectNulls={false}`).
  - Gaps longer than 2 × the series interval render a hatched `--chart-gap` band labelled
    "No data" (label shown if band ≥ 40 px wide), with tooltip "No reading 03:10–07:25".
  - Isolated valid points between gaps render as 3 px dots so they remain visible.
  - Values the API flags as questionable (e.g., source severity `ERROR` alongside a value) render as
    hollow points not joined to the line, tooltip "Source flagged this reading (ERROR)".
  - Zero rainfall is a real value: no bar, but tooltip reads "0.0 mm". Missing rainfall shows the
    gap band, tooltip "No reading".
- **Tooltip**: shared crosshair across stacked panels; white elevated card; header = full timestamp
  `24 Sep 2026, 01:45 MYT`; rows = series label, value + unit (`.num`), and for WL the official state
  at that value if the API provides it. Forecast rows prefixed "FloodGuard forecast".
- Accessibility: chart container `role="img"` with an `aria-label` summary ("Water level, last 24 h,
  4.62 to 5.00 m, currently 5.00 m, below Waspada"), plus a "View as table" toggle rendering the
  same data in a table.
- Sparklines: allowed only in dense tables when they add information (e.g., 6 h WL trend per
  station). 80 × 24 px, no axes, line only, gaps still broken, threshold not shown. Off by default.

## 23. Maps

**[depends: verified station coordinates]**. Library: MapLibre GL JS (vector, WebGL, accessible
controls) preferred; Leaflet acceptable if raster tiles are chosen. Decide at implementation; the
design is library-agnostic. Basemap: light, low-saturation vector style (roads light grey, water pale
blue `#DCEBF5`, labels muted); tile provider and licence to be verified and attributed. No satellite
default; optional satellite toggle only with a clear reason.

- **Initial view**: bounds fitted to all Penang stations (island + Seberang Perai) with 24 px padding;
  min zoom so the whole state fits; max bounds restricted loosely to northern Peninsular Malaysia.
- **District boundaries**: thin `#98A2B3` 1 px lines with district labels at low zoom, only if an
  official boundary dataset is sourced **[depends]**. Otherwise none.

**Markers** (SVG/symbol layers; sizes at default zoom):

| Aspect | Encoding |
|---|---|
| Sensor type | Shape: water level = square 12 px (`--radius-sm` 2 px); rainfall = circle 10 px; confirmed shared site = square with 5 px telemetry circle badge at top-right |
| Official state (WL only) | Fill: normal/caution/warning/danger solid; size steps 12 / 14 / 16 / 18 px; at ≥ 16 px the severity icon glyph is drawn inside in white/dark |
| Rainfall | Fill `--color-telemetry`; no severity |
| Freshness: Fresh | As above, 1.5 px white halo |
| Freshness: Delayed | As above + 1.5 px dashed `#475467` outer ring |
| Freshness: Stale | `--map-marker-muted` fill at 60%, dashed outline; official state not shown (it is outdated) — tooltip shows last known state with time |
| No data / Invalid | White fill, 1.5 px dashed `--map-marker-muted` outline, small `slash` glyph |
| FloodGuard risk **[depends]** | Not in fill (fill is JPS). Optional small outline diamond badge at bottom-right in risk colour, dashed; shown only when a "Show FloodGuard risk" toggle is on |
| Hover | Scale 1.15, `--shadow-2`-like halo, popover |
| Selected | 2 px primary ring with 2 px white gap, z-order top, label shown |
| Keyboard focus | Same ring as selected but focus-ring colour + dotted, plus popover |

- Draw order: Bahaya > Amaran > Waspada > normal > rainfall > stale/no data, selected always top.
- **Clustering**: off by default (≤ ~80 points). Enable only if marker overlap at the initial zoom
  hides stations; clusters show count and the worst official state as a ring, split on click.
- **Controls**: zoom in/out, "Fit to Penang" (`locate-fixed`), fullscreen optional; 32 px (44 touch)
  buttons, top-right, `--shadow-1`, labelled. No geolocation prompt on load; "Near me" only on user
  action if later required.
- **Keyboard/AT fallback**: markers are focusable in list order (sorted by severity) via an offscreen
  list synced with the map; Enter selects; Esc clears. The canvas has `aria-label="Map of Pulau
  Pinang monitoring stations"` and a visible "Skip map, go to station list" link. The List view is
  always one click away.
- **Attribution**: basemap attribution and "Station data: JPS Public Infobanjir" bottom-right.
- **Mobile**: map full-width, height `60vh` on Overview; Live map uses full remaining height with the
  station panel as a bottom sheet (peek shows name, value, state, freshness). Two-finger pan to avoid
  scroll traps when the map is embedded in a scrolling page.

## 24. Interaction States

Global rules for every interactive element:

| State | Rule |
|---|---|
| default | Meets 3:1 boundary contrast for controls, 4.5:1 for text |
| hover | Background `--color-hover` or darker tone; cursor pointer; no size change except map markers |
| active | Slightly darker bg; no shadows appear |
| focus-visible | 2 px `--color-focus-ring`, 2 px offset (inset in tables/lists); never suppressed |
| disabled | `--color-disabled-bg` + `--color-text-disabled`; `aria-disabled`; tooltip explains why when not obvious |
| loading | Keep layout size; spinner only inside buttons; skeletons for content; `aria-busy` |
| selected | `--color-primary-subtle` bg + primary 2 px indicator (left bar in lists, underline in tabs, ring on map) |
| validation-error | Danger border + message below with icon; announced via `aria-describedby`; focus moves to first invalid field on submit |
| unavailable-data | "—" + reason; control hidden if its whole feature depends on unavailable data, disabled with reason if only temporarily unavailable |

Motion: transitions `--motion-fast` (120 ms) for hover/colour, `--motion-base` (180 ms) for
popover/drawer, `--motion-slow` (240 ms) for bottom sheet. Easing `cubic-bezier(0.2, 0, 0, 1)`.
No looping or pulsing animations, including on Bahaya markers. `prefers-reduced-motion: reduce` →
durations 0, no shimmer, map fly-to replaced by jump-to.

## 25. Loading, Empty, Error and Offline States

| Situation | Treatment |
|---|---|
| Initial load | Skeletons matching layout; header and nav render immediately |
| Background refresh (polling) | No skeletons; keep data; header "Updated" time changes; subtle 2 px progress bar under header during fetch |
| Partial station outage | Affected rows show Stale/No data; summary "Not reporting" count; no page-level banner unless a whole source is down |
| Source listing unavailable (API reports source down) | Caution banner: "JPS water-level data hasn't been retrieved since 01:47. Values shown may be out of date." Stations keep last values with their real observation times; freshness chips update from the API |
| FloodGuard API unreachable | Neutral banner: "Can't reach FloodGuard service. Showing data from 01:47." + Retry. Data remains visible, visibly dated. Retries with backoff (TanStack Query defaults, capped) |
| Browser offline | Neutral banner: "You're offline. Showing data from 01:47." Auto-refresh on reconnect |
| Model not ready (`/ready` false or API says model unavailable) | Prediction sections show "Predictions unavailable — model not loaded." Observed data unaffected |
| Prediction on stale input | Per §16: unavailable with reason |
| Empty filter result | In-table empty state + "Clear filters" |
| No alerts | "No alerts in this period." (neutral, no celebratory copy) |
| Any station at Bahaya (official) | Danger banner on every page: `octagon-alert` "Bahaya level reached at 1 station: Sg. X (6.02 m, obs 01:45)" + link. Source label "JPS official". Persists while true |
| 404 station | "Station not found. It may have been removed from the source listing." + back to Stations |
| Gated feature | "Not available yet" page with one sentence on what is required (e.g. "Station locations have not been verified yet.") |

Never show an empty map, empty chart axes, or zeros in place of missing data.

## 26. Responsive Design

Breakpoints: `sm 640`, `md 768`, `lg 1024`, `xl 1280`, `2xl 1440`, `3xl 1920`.

| Element | ≥ 1920 (Full HD) | 1440 × 900 (laptop) | 768–1023 (tablet) | 360–430 (mobile) |
|---|---|---|---|---|
| Sidebar | Expanded 232 px | Expanded 232 px (user-collapsible to 64) | Collapsed 64 px icons + tooltips; expands as overlay | Hidden; hamburger in header opens left drawer |
| Header | Title + updated + refresh | Same | Same, breadcrumb truncated | 56 px: menu button, page title (`text-lg` 600), refresh icon button |
| Overview | Strip (6 cells) · map 8 cols + list 4 cols · alerts | Strip (4–5 cells) · map 7 + list 5 | Strip 2 rows × 3 · map full width 420 px · list below | Strip as 2×2 compact grid · "Needs attention" list first · map 60vh below · alerts |
| Live map | Map + 360 px panel | Map + 360 px panel | Map full; panel as right drawer 360 px over map | Map full; bottom sheet panel; filters in bottom sheet behind "Filters (2)" button |
| Stations table | All columns | All; station name truncates | Hide District (moves under name), abbreviate Type | Card-list transform: name + state chip / value + unit / obs time + freshness; filters in sheet |
| Station detail | Main + 320 px right rail | Main + rail | Single column: thresholds after measurements | Order: name · official state + value + obs time + freshness · FloodGuard horizons · chart · thresholds · quality. Tabs optional |
| Predictions | Station × 3 horizons | Same | Single-horizon mode default (+60) with segmented control | Cards per station: name, 3-row mini horizon table, input quality |
| Alerts | List + 480 px drawer | Same | List; drawer 100% width ≤ 900 | Stacked alert rows (headline, chips, time); detail full-screen sheet |
| Charts | Height 320 (WL) + 120 (rain) | 280 + 100 | 240 + 96 | 200 + 80, fewer ticks, range control full width |
| Filters | Inline toolbar | Inline toolbar (wraps) | Toolbar + overflow "More filters" | "Filters" button → bottom sheet |

Mobile priorities (top of screen): current official state and value, observation time + freshness,
FloodGuard predictions, then trend and metadata. Touch targets ≥ 44 × 44 px. No horizontal page
scroll at 360 px.

## 27. Accessibility

Target WCAG 2.2 AA.

- **Landmarks**: `header`, `nav[aria-label=Main]`, `main#main`, `aside` for rails/panels; skip link.
- **Headings**: one `h1`; logical `h2`/`h3`.
- **Keyboard**: all functionality reachable; visible focus (2.4.7) not obscured by sticky header or
  sheets (2.4.11); logical tab order; Esc closes overlays; focus trap in dialogs/drawers with return
  focus; roving tabindex in tabs/segmented controls; map markers reachable (see §23).
- **Contrast**: text ≥ 4.5:1 (large ≥ 3:1), UI boundaries and markers ≥ 3:1 against adjacent colours
  (white marker halo guarantees this on the basemap). Tokens in §6 are pre-checked.
- **Not colour alone** (1.4.1): every state = colour + icon + text; markers use shape and size too;
  chart series differ by line style as well as colour.
- **Tables**: semantic markup, `scope`, `aria-sort`, captions.
- **Forms**: visible labels, `aria-describedby` for help/errors, `aria-invalid`.
- **Icon buttons**: `aria-label`; decorative icons `aria-hidden="true"`.
- **Live regions**: new official Bahaya banner uses `role="alert"`; routine polling updates are
  **not** announced (avoid chatter); "Updated 01:47" is `aria-live="polite"` only on manual refresh.
- **Charts/maps**: text alternative summary + table/list view.
- **Target size** (2.5.8): ≥ 24 × 24 CSS px minimum everywhere; 44 × 44 px on touch layouts.
- **Motion**: honour `prefers-reduced-motion`; no auto-playing animation.
- **Zoom/reflow**: usable at 200% zoom and 320 px width (1.4.10) — the mobile layout handles this.
- **Language**: `lang="en-MY"`; Malay JPS terms wrapped with `lang="ms"`.
- **Time**: timestamps in `<time datetime="2026-09-24T01:45:00+08:00">`.
- Testing: axe-core in component tests and Playwright E2E; manual keyboard pass per view; NVDA +
  Chrome spot checks on Stations table, Station Detail, map fallback.

## 28. Content and Microcopy

**Voice**: plain, operational, factual. Sentence case. No exclamation marks, no hype, no
anthropomorphic model language ("the AI thinks").

| Use | Avoid |
|---|---|
| Last observation · Obs 01:45 MYT | Last seen, Live now |
| Retrieved 01:47 (when FloodGuard fetched from JPS) | Synced |
| Updated 01:47 (when this page got data from the API) | Real-time |
| Observed rainfall · 1 h rainfall · Since midnight | Rain intensity score |
| Water level | River height index |
| 30 min prediction · Flood-risk probability | AI prediction, Smart forecast, Intelligence score |
| FloodGuard forecast | Official forecast |
| Model contributors | Why it will flood, Root cause, Insights |
| Data stale · No reading available · Invalid time | Offline (unless the source says so), N/A, 0 |
| Prediction unavailable — input data stale | Error, Something went wrong |
| Waspada / Amaran / Bahaya (JPS) | Low / Medium / High for official states |

- **Terms**: "Station" for a JPS monitoring record; "site" only when the station master confirms a
  shared physical site. Sensor types: "Rainfall", "Water level".
- **Official labels**: keep Malay JPS threshold terms verbatim; English gloss in legend/tooltip:
  Waspada (alert), Amaran (warning), Bahaya (danger).
- **Station names**: verbatim from source, including "(F2)", "(RHN)" suffixes; do not "clean" them.
- **Units**: always shown; `m` with 2 decimals, `mm` with 1 decimal, probabilities as integer `%`,
  durations "55 min", "10 h 30 min". Thin space between value and unit. Negative/zero values shown as
  received.
- **Dates/times**: 24-hour clock, Malaysian day-month order. Today: `01:45`; other days:
  `23 Sep, 15:15`; full: `24 Sep 2026, 01:45 MYT`. Relative age alongside where helpful: `01:45 ·
  15 min ago`. Month names in English short form.
- **Timezone disclosure**: JPS timestamps have no declared timezone; FloodGuard assumes Malaysia time.
  Show "MYT" on full timestamps and, in the time tooltip and Data status page: "Source time assumed to
  be Malaysia time (UTC+8); JPS does not state a timezone." Remove this note only when verified.
- **Disclaimer** (sidebar footer, prediction sections, Data status): "FloodGuard is not an official
  warning service." — short, factual, always present, never in a modal.
- **Numbers never claimed**: no model accuracy, recall or "x% accurate" copy in the operational UI
  unless served by the API from a recorded evaluation with its dataset/model version.

## 29. Design Tokens

Focused token set; implement as CSS custom properties in `frontend/src/styles/tokens.css` and map
into Tailwind (`@theme` in Tailwind v4 or `theme.extend` in v3).

```css
:root {
  /* Typography */
  --font-sans: "Inter", "Geist", -apple-system, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
  --font-mono: "JetBrains Mono", "Geist Mono", ui-monospace, "SF Mono", Consolas, monospace;
  --text-2xs: 11px;  --leading-2xs: 16px;
  --text-xs: 12px;   --leading-xs: 16px;
  --text-sm: 13px;   --leading-sm: 20px;
  --text-base: 14px; --leading-base: 20px;
  --text-md: 16px;   --leading-md: 24px;
  --text-lg: 18px;   --leading-lg: 28px;
  --text-xl: 20px;   --leading-xl: 28px;
  --text-2xl: 24px;  --leading-2xl: 32px;
  --text-metric: 28px; --leading-metric: 32px;
  --weight-regular: 400; --weight-medium: 500; --weight-semibold: 600;

  /* Neutrals */
  --color-bg: #F6F8FB;
  --color-surface: #FFFFFF;
  --color-surface-subtle: #F9FAFB;
  --color-surface-sunken: #F2F4F7;
  --color-surface-elevated: #FFFFFF;
  --color-border: #E4E7EC;
  --color-border-strong: #8A94A6;
  --color-text-primary: #172033;
  --color-text-secondary: #475467;
  --color-text-tertiary: #667085;
  --color-text-disabled: #98A2B3;
  --color-text-inverse: #FFFFFF;

  /* Interaction */
  --color-primary: #2563EB;
  --color-primary-hover: #1D4ED8;
  --color-primary-active: #1E40AF;
  --color-primary-subtle: #EFF6FF;
  --color-primary-border: #BFDBFE;
  --color-hover: #F2F4F7;
  --color-focus-ring: #2563EB;
  --color-disabled-bg: #F2F4F7;

  /* Telemetry */
  --color-telemetry: #0891B2;
  --color-telemetry-text: #0E7490;
  --color-telemetry-subtle: #ECFEFF;

  /* Official JPS states (water level) + destructive */
  --color-normal: #16A34A;  --color-normal-text: #15803D;  --color-normal-subtle: #F0FDF4;
  --color-caution: #F59E0B; --color-caution-text: #B45309; --color-caution-subtle: #FFFBEB;
  --color-warning: #EA580C; --color-warning-text: #C2410C; --color-warning-subtle: #FFF7ED;
  --color-danger: #DC2626;  --color-danger-text: #B91C1C;  --color-danger-subtle: #FEF2F2;

  /* FloodGuard-derived */
  --color-derived: #475467;
  --color-prediction: #344054;
  --color-prediction-band: rgba(52, 64, 84, 0.10);

  /* Charts */
  --chart-grid: #EEF0F3;
  --chart-axis: #8A94A6;
  --chart-rainfall: #0891B2;
  --chart-water-level: #1D4ED8;
  --chart-prediction: #344054;
  --chart-now: #667085;
  --chart-gap: #F2F4F7;

  /* Map */
  --map-water: #DCEBF5;
  --map-marker-stroke: #FFFFFF;
  --map-marker-muted: #98A2B3;
  --map-marker-selected-ring: #2563EB;

  /* Spacing (4px unit) */
  --space-0-5: 2px; --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 20px; --space-6: 24px; --space-8: 32px; --space-10: 40px; --space-12: 48px;

  /* Radius, border, elevation */
  --radius-sm: 4px; --radius-md: 6px; --radius-lg: 8px; --radius-xl: 12px; --radius-full: 9999px;
  --border-width: 1px;
  --shadow-1: 0 1px 2px rgba(16, 24, 40, 0.06);
  --shadow-2: 0 4px 12px rgba(16, 24, 40, 0.08), 0 1px 3px rgba(16, 24, 40, 0.06);
  --shadow-3: 0 16px 32px rgba(16, 24, 40, 0.12);
  --focus-ring: 0 0 0 2px var(--color-surface), 0 0 0 4px var(--color-focus-ring);

  /* Icons */
  --icon-xs: 12px; --icon-sm: 16px; --icon-md: 20px; --icon-lg: 24px;

  /* Component dimensions */
  --sidebar-width: 232px; --sidebar-width-collapsed: 64px;
  --header-height: 56px; --toolbar-height: 48px;
  --control-height-sm: 32px; --control-height-md: 36px; --control-height-lg: 40px;
  --touch-target: 44px;
  --table-header-height: 36px; --table-row-height: 40px; --table-row-height-2line: 48px;
  --chip-height: 20px;
  --map-panel-width: 360px; --detail-rail-width: 320px; --drawer-width: 480px;

  /* Motion */
  --motion-fast: 120ms; --motion-base: 180ms; --motion-slow: 240ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);

  /* Z-index */
  --z-base: 0; --z-sticky: 10; --z-map-controls: 15; --z-sidebar: 20; --z-header: 30;
  --z-dropdown: 40; --z-drawer: 50; --z-dialog: 60; --z-toast: 70; --z-tooltip: 80;
}

@media (prefers-reduced-motion: reduce) {
  :root { --motion-fast: 0ms; --motion-base: 0ms; --motion-slow: 0ms; }
}

.num { font-variant-numeric: tabular-nums; }
```

Breakpoints (Tailwind `screens`): `sm: 640px, md: 768px, lg: 1024px, xl: 1280px, 2xl: 1440px,
3xl: 1920px`.

Semantic status mapping (TypeScript, shared by chips, markers, legend):

```ts
export type OfficialState = "normal" | "waspada" | "amaran" | "bahaya";          // from API
export type Freshness = "FRESH" | "DELAYED" | "STALE" | "NO_DATA" | "INVALID";   // from API

export const officialStateStyle: Record<OfficialState, { label: string; gloss: string; tone: "normal" | "caution" | "warning" | "danger"; icon: string }> = {
  normal:  { label: "Normal",  gloss: "below Waspada", tone: "normal",  icon: "circle-check" },
  waspada: { label: "Waspada", gloss: "alert",         tone: "caution", icon: "circle-alert" },
  amaran:  { label: "Amaran",  gloss: "warning",       tone: "warning", icon: "triangle-alert" },
  bahaya:  { label: "Bahaya",  gloss: "danger",        tone: "danger",  icon: "octagon-alert" },
};

export const freshnessLabel: Record<Freshness, string> = {
  FRESH: "Fresh", DELAYED: "Delayed", STALE: "Stale", NO_DATA: "No data", INVALID: "Invalid time",
};
```

The exact API enum values for official state and FloodGuard risk are defined by the backend
schema **[depends: Phase 8 API contract]**; the frontend maps them here and nowhere else.

## 30. Frontend Implementation Guidance

- **Stack** (recommendation; confirm in an ADR when Phase 11 starts): React + TypeScript (strict),
  Vite, React Router, TanStack Query for server state (polling via `refetchInterval` aligned to the
  ingestion cadence, served by config — not hardcoded), Tailwind CSS mapped to the tokens above,
  Radix UI primitives (or shadcn/ui restyled to these tokens) for accessible dialogs, dropdowns,
  tabs, tooltips; Lucide React icons; one chart library; MapLibre GL JS.
- **Structure** (`docs/14_FOLDER_STRUCTURE.md`): `frontend/src/{components,features,pages,services,hooks,types}`.
  `components/` = design-system primitives (Button, StatusChip, FreshnessChip, DataTable, Banner,
  EmptyState, Skeleton, TimeLabel, Measurement). `features/` = stations, map, predictions, alerts,
  status. `services/` = typed API client (types generated from the FastAPI OpenAPI schema).
- **Single sources of truth**: `tokens.css`; `status.ts` (official/freshness/risk → label, tone,
  icon); `format.ts` (units, decimals, times in `Asia/Kuala_Lumpur` via `Intl.DateTimeFormat`,
  relative age). No component formats numbers or times itself.
- **Required primitives before pages**: `Measurement` (value + unit + obs time + freshness, handles
  null → "No reading available"), `OfficialStateChip`, `PredictionRiskChip`, `FreshnessChip`,
  `SourceLabel` ("JPS" / "FloodGuard"), `TimeLabel` (`<time>` + tooltip + MYT disclosure).
  Using these makes the data-semantics rules hard to break.
- **Business logic stays server-side**: no threshold comparisons, freshness computation, feature
  building or risk thresholds in the browser. If the API doesn't provide it, request it from the
  backend rather than computing it.
- **Feature gating**: a capabilities check (e.g., from `/api/v1/monitoring` or `/api/v1/model`)
  decides which nav items and sections render. No mock data in production builds; fixtures only in
  tests/Storybook, clearly named, using recorded real shapes.
- **Security**: no secrets in the bundle; API base URL via `VITE_API_BASE_URL`; render all source
  strings as text (never `dangerouslySetInnerHTML` — station names come from scraped HTML).
- **Testing**: component tests (Vitest + Testing Library + axe) for every primitive's states; E2E
  (Playwright) for Overview → Station Detail, filters, stale/unavailable prediction states, API-down
  banner, keyboard map fallback; visual checks at 360, 768, 1440, 1920 px.
- **Performance**: route-level code splitting (map and charts lazy-loaded); list ≤ 100 rows needs no
  virtualisation; target LCP < 2.5 s on laptop; avoid re-rendering the map on every poll (update
  source data only).

## 31. Anti-Patterns

Prohibited:

1. **Dark theme as default** (or any dark "command-centre" look).
2. **Decorative gradients** — backgrounds, buttons, cards, chart fills, logos.
3. **Glassmorphism**, frosted/blurred panels, translucent layered cards.
4. **Neon, glow, pulsing** effects, including pulsing danger markers.
5. **Giant metric cards** — oversized numbers in individual cards; > 28 px text.
6. **Excessive pills** — fully rounded chips/buttons/containers; chip soup on every row.
7. **Deeply nested cards** — bordered boxes inside bordered boxes.
8. **Oversized rounded corners** (> 12 px on containers).
9. **Excessive shadows** on static content.
10. **Fake AI content** — "AI insights", generated summaries, confidence theatre, sparkles icons,
    chat widgets.
11. **Unsupported predictions** — any probability, forecast or risk not returned by the API; any
    prediction on stale/invalid input; any accuracy claim without a recorded evaluation.
12. **Unnecessary charts** — donuts, gauges, radar, 3D, KPI sparklines with no axis meaning,
    dashboard trend charts without thresholds or context.
13. **Duplicated information** — the same number in the strip, a card and a table on one screen.
14. **Decorative icons** — icons without meaning, icons > 24 px, mixed icon families.
15. **Generic admin-template styling** — purple/indigo defaults, stock card grids, avatar/bell
    headers with no function, lorem/placeholder numbers.
16. **Hidden timestamps** — any live value without its observation time or freshness.
17. **Unlabelled risk colours** — any coloured status without icon + text; legends missing.
18. **Mixing observed and predicted data** — same column, same series, same chip style, or
    predictions phrased as official JPS warnings.
19. **Missing shown as zero** — `-9999`, gaps or no-data rendered as `0` or bridged with a line.
20. **Invented rainfall severity** or any status JPS/API doesn't provide.
21. **Internal IDs as names** — `jps_internal_id` as the primary label.
22. **Browser-side business logic** — thresholds, freshness or risk computed in React.
23. **Uppercase headings and status shouting** (`FRESH`, `DANGER`) in the UI.
24. **Placeholder maps or widgets** for capabilities that don't exist yet.

### Approved exception (UI/UX refresh)

3D is permitted **only on the map**: camera tilt, extruded basemap buildings and optional terrain/hillshade as geographic
context, with a 2D toggle. Station data is never extruded and charts stay 2D. Depth elsewhere comes from the elevation scale
(canvas → shell → panel → overlay), never from gradients, glow or blur.
