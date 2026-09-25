# FloodGuard Penang — React Operational UI

React 19 + TypeScript (strict) + Vite + React Router + TanStack Query + Tailwind CSS v4 + Lucide + MapLibre GL + Recharts.
Consumes the FloodGuard FastAPI only (ADR-0007/0008); no ML, threshold, freshness or risk logic runs in the browser.

## Design sources

- `00_SHARED_DESIGN_SYSTEM.md`, `01_OVERVIEW.md` … `07_DATA_STATUS.md` — page specs (source of truth).
- `design.md` — full design system and data-semantics rules.
- `ChatGPT Image …-1..7.png` — visual references only (composition, spacing, hierarchy).

## Run

```bash
npm install
npm run dev          # against VITE_API_BASE_URL (see .env.example)
npm run dev:mock     # against the SYNTHETIC test API in e2e/mock-api (port 8787)
npm run lint && npm run typecheck && npm test && npm run build
npm run e2e          # production build + synthetic API, Chrome channel, axe checks at 1440 and 360 px
```

## API contract

The FastAPI service does not exist yet. `src/api/types.ts` records the contract this UI expects, derived from
`AGENTS.md` §18, `docs/02_ARCHITECTURE.md`, `docs/STATION_MASTER_DESIGN.md` and `docs/18_ALERTING_PLAN.md`.
Regenerate it from the OpenAPI schema when the API lands.

| Endpoint | Used by | Notes |
|---|---|---|
| `GET /api/v1/stations`, `/api/v1/stations/{site_id}` | all pages | Sites with sensors, latest observation, API-evaluated `official_state`, `freshness`, thresholds |
| `GET /api/v1/observations?sensor_id&hours` | Station detail | 5-min series; missing values as `MISSING`, source `ERROR` as `SOURCE_FLAGGED` |
| `GET /api/v1/predictions` | Predictions, Map, Station detail | Per-site 30/60/120 min, status `AVAILABLE`/`DEGRADED`/`UNAVAILABLE` |
| `GET /api/v1/alerts?hours` | Overview, Alerts | Categories kept distinct; Active/Resolved only (no operator actions) |
| `GET /api/v1/monitoring` | Data status, Stations | Sources, services, freshness rule, quality issues |
| `GET /health`, `GET /ready` | Data status | |

A `404`/`501` response marks a capability as **not built yet**: the UI shows "not available yet" and disables
dependent filters. Network failure shows an error with Retry. There is no production fallback data.

## Test data

`e2e/mock-api/fixtures.mjs` is **synthetic** (invented names, coordinates and values). JPS content is
permission-required (`docs/DATA_LICENSING_AND_ACCESS.md`), so no real station data is committed. The fixtures are
used only by Vitest, Playwright and `npm run dev:mock`; nothing under `src/` imports them.

## Visual system (UI/UX refresh)

- **Soft depth, no glass:** neutral canvas → raised rounded shell (≥1024 px) → flat bordered panels → one `raised` panel per page
  (situation hero, observation card, selected-station rail) → floating map overlays. Hover lift only on clickable cards.
- **3D is map-only:** `StationMap mode="3d"` tilts the camera, extrudes basemap buildings and, when `VITE_TERRAIN_URL` is set,
  adds terrain + hillshade. A 2D/3D toggle is remembered per browser. Data charts stay 2D (design.md bans 3D charts).
- **Threshold meter** (`ThresholdMeter`) places the API-reported level between the JPS thresholds; it never decides a state.
- **InfoTip / Popover** replace repeated helper sentences and secondary filters; a sticky `StatusStrip` replaces page banners.
- Motion: 180–200 ms fades/lifts and a 500 ms camera ease on selection, all disabled under `prefers-reduced-motion`.

## Intentional differences from the reference images

- **No photo hero.** No licensed Penang image exists in the repo; the Overview hero pairs the situation summary with the live 3D station map.
- **Threshold legend without values.** JPS thresholds are per station; the images' single Penang-wide ranges would be invented.
- **Rainfall has no official state.** Images show Waspada/Amaran on rainfall rows; JPS publishes no rainfall thresholds.
- **FloodGuard risk uses High/Medium/Low dashed chips**, never Normal/Waspada/Amaran/Bahaya or "Likely to remain Normal".
- **No METMalaysia source, uptime sparklines, "vs previous period" deltas or donut charts.** None are backed by the API.
  Distributions are stacked bars.
- **No advice copy** ("take preventive action"); FloodGuard is not a warning authority.
- **"Current" instead of "Real-time"** in the Overview subtitle: ingestion is 15-min polling (ADR-0009).
- **District selector is in the filter bar**, not repeated in the header, on Live Map; Stations uses type tabs instead of a duplicate sensor-type select.
- **Freshness rule text comes from the API**; images' "≤ 1 hour" / "30–60 min" bands differ from the provisional rule (fresh ≤ 30 min, stale > 180 min).

## Backend dependencies still open

Station and observation endpoints, the prediction service and label definitions (Phase 3/5/10), alert schema and
service (Phase 8/11), monitoring endpoint, and a licensed basemap (`VITE_MAP_STYLE_URL`, OpenFreeMap by default;
verify terms before public use). JPS display permission is required before any public deployment.
