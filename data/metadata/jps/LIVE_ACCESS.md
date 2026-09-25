# JPS Public Infobanjir — Live Access (Pulau Pinang)

Verified 2026-09-24, 07:55–08:23 (+08:00). Tool: `scripts/probe_jps_live.py`, which is one-shot by
default; `--samples N --interval S` is bounded to N ≤ 20 and S ≥ 60 s. Requests for this task:
**47**, sequential, ≥ 2 s apart, UA `FloodGuard-Penang-discovery/0.1 (research)`. No 403/429, no
throttling, no CAPTCHA. Evidence: `live_sampling_20260924_summary.json` plus two raw snapshots,
`raw/searchresultrainfall_PNG_20260924T075653+0800.html` and `raw/aras-air-data_PNG_20260924T075655+0800.html`.

`observation_time` is the source's "Kemaskini Terakhir" value. It has no declared timezone and is
never replaced by retrieval time. `retrieved_at` is the local clock at request time (+08:00). All
`fg_*` fields are FloodGuard-derived.

## Endpoints (re-verified from live page JS — unchanged)

| | Rainfall | Water level |
|---|---|---|
| State page JS builds | `/wp-content/themes/shapely/agency/searchresultrainfall.php?state=…` | `/index.php/aras-air/data-paras-air/aras-air-data/?state=…` |
| Request used | `GET …/searchresultrainfall.php?state=PNG&district=ALL&station=ALL&loginStatus=0&language=0` | `GET …/aras-air-data/?state=PNG&district=ALL&station=ALL` |
| Identifiers needed | state code `PNG`; optional `district` (name) and `station` filters. No per-station ID needed | same |
| Identifiers returned | `jps_internal_id` (rf-graph link), display "ID Stesen", name, district | `jps_internal_id` (wl-graph link), display ID, name, district, basin |
| Response | HTML table fragment, 56 rows, ~31 KB | HTML table fragment, 22 rows, ~20 KB |
| Auth / cookies | None. `Set-Cookie: PHPSESSID` is sometimes sent, but requests without cookies work | same |
| HTTP status | 200 on all 14 samples | 200 on all 14 samples |
| `Content-Type` | `text/html; charset=UTF-8` | same |
| `Cache-Control` | `max-age=0, no-cache, no-store` (+ `Pragma: no-cache`, `Expires` = `Date`) | same |
| `ETag` / `Last-Modified` | **absent** | **absent** |
| Conditional request | `If-Modified-Since: <Date>` → **200, full body** (not honoured). No ETag to test `If-None-Match` | same (1 request each) |
| Source-generated time | Per-row "Kemaskini Terakhir" only. Page footer "Kemaskini Terakhir" is a page-level value that ran ahead of the clock (e.g. `08:00` at 07:55) and is not used | same |
| CDN | Akamai; `Server-Timing: cdn-cache; desc=MISS` on the 4 listing responses captured with full headers | same |

## Fields per strategy

| Strategy | Rainfall fields | Water-level fields | Requests per Penang poll | Freshness vs listing | Parsing robustness |
|---|---|---|---|---|---|
| **(a) State listing** | ID, name, district, observation time, 6 daily totals, since-midnight total, latest 1 h total | ID, name, district, basin, sub-basin, observation time, level (m), Normal/Waspada/Amaran/Bahaya | **2** (1 RF + 1 WL; the state page only once per run for the district list) | reference | HTML; fixed headers checked. Malformed RF markup (no opening `<tr>`) is handled |
| (b) Per-station graph page | Page is HTML with JS only; it calls the default JSON (3-day RF, 7-day WL ≈ 90–200 KB) | same plus per-reading severity | 1–2 per station → **~78–156** | not faster (it calls the same JSON as c) | JSON, but large payloads |
| (c) Date-range JSON, last 2 h | 5-min `raw` (per-interval mm), `cdaily`, `cyearly`, … | 5-min `raw/ecm/clean/final`, `severity`, thresholds in `info` | 1 per station → **78** | Same latest time as the listing. 4 stations checked at 08:21: RF 27603 08:15 = listing, RF " 5402002_" 07:30 = listing, WL 27587 and BUMBUNGLIMA padded with `-9999` exactly from the listing time up to the requested end (1 and 10 slots) | JSON, well-formed; `-9999` padding to the requested end |

**Recommendation: (a) state listing.** It is 2 requests per poll for all 78 Penang rows and has the
required fields (observation time, rainfall values, water level, thresholds). Neither (b) nor (c)
gave newer observations. Use (c) only as a **targeted backfill** after gaps or outages, because it
adds 5-min resolution, per-interval rainfall, and severity at 1 request per station.

## Update behaviour (measured)

Setup: 14 samples per sensor, 105 s apart, 07:56:53 → 08:19:40, RF and WL alternated.

| | Rainfall | Water level |
|---|---|---|
| Stations per sample | 56 in all 14 (set identical) | 22 in all 14 (set identical) |
| Stations whose time advanced during the window | 45 of 56 | 19 of 22 |
| "(F2)" stations | 28 advanced **together** by exactly 15 min (07:45 → 08:00 → 08:15). 1 ran one cycle behind (07:30 → 08:00 → 08:15). 6 did not advance (5 aged > 180 min, plus `27692` at 06:15) | 15 advanced together (07:45 → 08:00 → 08:15). 2 did not (26460, 27608) |
| Other stations (7-digit/code IDs, "(RHN)") | Advanced **asynchronously**, steps of 10, 15, 20, 30 min (e.g. 07:00 → 07:10 → 07:30) | same pattern (07:10 → 07:40, 07:25 → 07:40) |
| Timestamp alignment | All observation times fall on 5-min boundaries (55 of 56 RF and 20 of 22 WL on 15-min boundaries at the first sample) | same |
| When batches appeared | :00 batch between 08:05:38 and 08:07:23; :15 batch between 08:17:53 and 08:19:38 | :00 batch between 08:05:40 and 08:07:25; :15 batch between 08:17:55 and 08:19:40 |
| Publication lag, F2 (bounds: previous vs first `retrieved_at` − obs time) | lower 2–5 min, upper 4–7 min (n = 58) | lower 2–5, upper 4–7 (n = 30) |
| Publication lag, other | lower 2–55 (median 27), upper 4–57 (median 29), n = 23 | lower 27–37, upper 29–39, n = 4 |
| Value changes | none; `rainfall_1h_mm` = 0.0 on all 56 rows in all samples (dry period, so rainfall dynamics were not observed) | 10 stations changed level, by up to 0.28 m (27665: −0.03 → −0.31) |

Lag uses `retrieved_at − observation_time`, **assuming** the source time is Asia/Kuala_Lumpur (not
declared by JPS; consistent with every capture so far).

## Missing and odd values in current listings (every sample)

| Count per sample | Rainfall | Water level |
|---|---|---|
| Zero values | `rainfall_1h_mm` = 0.0 on 56/56 (zero = data, not missing) | `water_level_m` = 0.00 on 1 (`5403043_`) |
| Negative values | — | yes (e.g. 27613 −0.04 to −0.20, 27665 −0.03 to −0.31); kept as published |
| Blank cells | 0 | 0 |
| `-9999` | 0 | 0 |
| Non-numeric value cells | 0 | 0 |
| Missing observation time | 0 | 0 |
| Display ID "No Data" | 2 | 1 |
| Age > 180 min | 5 (27608 03:45, 27616, 27643, 27648, 27672 from 23/09) | 2 (26460 23/09 15:15, 27608 03:45) |
| `ERROR` severity | not present in listings (history endpoints only) | not present in listings |

Status counts at the last sample (08:19): RF FRESH 35 / DELAYED 16 / STALE 5; WL FRESH 15 /
DELAYED 5 / STALE 2. DELAYED rows were non-F2 stations aged 34–64 min, plus RF `27692` Kg. Kebun
Baru (F2), which stayed at 06:15 (124 min) throughout. See the summary JSON for the per-sample series.

## Thresholds

All 22 water-level rows carried all four thresholds (Normal/Waspada/Amaran/Bahaya) in all 14
samples, with **no changes** during the window. This says nothing about whether thresholds change
over longer periods or whether historical values are kept.

## Failure behaviour (3 requests)

| Request | Status | Body |
|---|---|---|
| RF listing `state=XXX` | 200 `text/html` | HTML fragment (12,656 B) whose `<tbody>` holds one row `<td colspan='15'>Tiada Data</td>` |
| WL listing `station=NOSUCHSTATION` | 200 `text/html` | HTML fragment (7,481 B) whose `<tbody>` holds `<td colspan='18'>Tiada Data</td>` |
| WL history `station=99999999` | 200 `text/html` | `{"count":},]}No result` |

Errors are signalled in the **body, not the HTTP status**. The parsers report `Tiada Data` as a
schema error (exit 2) and "No result" as zero rows.

## Freshness design (FloodGuard-derived, provisional)

Defined once in `scripts/_jps_common.py` (`LIVE_RULES`, `fg_age_minutes`, `fg_live_status`):

- `fg_age_minutes` = `retrieved_at − observation_time` (source time assumed +08:00), floored.
  This is a different quantity from the inventory's `fg_freshness_minutes` (newest row in the same
  response minus the row), so the two keep separate names.
- Per measurement type: `expected_interval_minutes = 15`, `allowed_lag_minutes = 15`,
  `stale_after_minutes = FG_STALE_AFTER_MINUTES = 180` (**provisional**, unchanged).
- `fg_live_status`:
  - `INVALID`: observation time missing or unparseable, or more than 5 min in the future.
  - `NO_DATA`: the primary value (`rainfall_1h_mm` or `water_level_m`) is blank, `-9999` or non-numeric.
  - `FRESH`: age ≤ 30 min.
  - `DELAYED`: age 31–180 min.
  - `STALE`: age > 180 min.
- Evidence behind the numbers:
  - The synchronised F2 group (28 RF + 15 WL) was aged 4–20 min across the cycle (07:45 still newest at 08:05:38), so it stays FRESH when healthy.
  - One RF F2 station ran one cycle behind (up to 35 min, DELAYED for a few samples).
  - Non-F2 stations were aged 4–67 min, so they often show DELAYED. Per-station expected intervals should replace the per-sensor value once a station master exists.
  - Apart from 27692 (101–124 min), nothing aged between 67 and 274 min was observed, so 180 is not evidence-tuned.
- Zero rainfall is valid data and never NO_DATA.

## Polling interval

The source publishes the F2 network every 15 min, about 3–7.5 min after the quarter-hour.
Non-F2 stations publish asynchronously on 5-min-aligned times.

**Recommended: poll both listings every 5 min.** That is 2 requests per poll and 576 per day. Each
F2 batch is captured within ≤ 5 min of appearing, and asynchronous non-F2 updates are picked up
without polling faster than the source's finest timestamp resolution (5 min).

Cheaper alternative: 4 polls per hour at quarter-hour + 8 min. That covered both batches observed,
but only 2 batch boundaries were seen, so it is less proven. Do not poll faster than every 5 min.

## Production recommendation (proposed, not implemented)

Official JPS state listings → scheduled Python poll (5 min) → store raw response bytes with
`retrieved_at` → validate (header/cell contract, district list, numeric fields) → classify
(`fg_live_status`) → deduplicate → PostgreSQL.

- **Proposed observation uniqueness key:** `source + jps_internal_id + measurement_type + observation_time`.
  `jps_internal_id` alone is insufficient: 13 IDs are shared by RF and WL, and every poll repeats
  the same observation until the source advances.
- Keep `retrieved_at` (first-seen) separately; later polls that repeat an observation are duplicates, not new data.
- Use the date-range JSON endpoint only for targeted backfill after outages.
- **Kafka/MQTT not justified:** 2 small HTTP requests every 5 min and a 15-min source cadence (ADR-0009, polling first).

## Unknowns

- Behaviour during rain: `rainfall_1h_mm` stayed 0.0 throughout, so how rainfall values update is unobserved.
- Only a 23-min window was sampled, with 2 F2 batch boundaries; night/day or load variation is unknown.
- Whether non-F2 stations have a fixed cadence per station.
- Source timezone (assumed +08:00).
- Meaning of the page-footer time.
- Rate limits beyond ~1 request/min (none were hit).
- Licensing/terms for automated polling: no JPS permission exists; see `docs/DATA_LICENSING_AND_ACCESS.md` (PERMISSION REQUIRED). Raw snapshots are local-only (git-ignored).
