# JPS Public Infobanjir — Historical Availability (Pulau Pinang)

Feasibility investigation, 2026-09-24 (Asia/Kuala_Lumpur). No bulk download; no datasets built.
Tool: `scripts/probe_jps_history.py` (one station, one window per run; default cap 7 days,
`--allow-wide` cap 31 days). Requests for this investigation: **66** sequential GETs, ≥ 2 s apart,
UA `FloodGuard-Penang-discovery/0.1 (research)`. Every response was HTTP 200: no 403/429, no
throttling, no CAPTCHA, no auth. Raw evidence (small) in `raw/history_*`.

`jps_internal_id` is treated as a site ID (the graph-link `stationid`), not a sensor key. The same
ID is accepted by both endpoints for the 13 shared sites.

## Mechanism

Both official station graph pages (`/index.php/rf-graph/?stationid=…`, `/index.php/wl-graph/?stationid=…`)
build the date-range URL in page JS from the datetime pickers (format `DD/MM/YYYY HH:mm`). With
no range selected they call a fixed "last N days" endpoint instead.

| Aspect | Rainfall | Water level |
|---|---|---|
| Date-range endpoint | `GET /wp-content/themes/enlighten/query/searchresultrainfalldthourlylead.php` | `GET /wp-content/themes/enlighten/query/searchresultwaterleveldtlead.php` |
| Params | `extra=` (empty), `station`, `from`, `to`, `datafreq` | `station`, `from`, `to`, `datafreq` (no `extra`) |
| Identifier | `jps_internal_id` (e.g. `27608`, `25965`) | `jps_internal_id` (e.g. `27608`, `5302004_`) |
| Measurement-type param | none; the endpoint path selects the sensor | none; the endpoint path selects the sensor |
| Start/end format | `DD/MM/YYYY HH:mm`, source-local, **inclusive** at both ends (1 day at 5 min = 289 rows) | same |
| `datafreq` (5/15/60 in UI) | Does **not** change row spacing (always 5 min). **Does change `clean`**: at 5, `clean` = per-5-min increment; at 15, `clean` = trailing 15-min sum (see Semantics) | Row spacing unchanged at 15 (289 rows, 5 min) |
| Default (no range) | `getrainfalllast3dayslead.php?extra=&station=…` (~3 days) | `getwaterlevellast7dayslead.php?extra=&station=…` (~7 days, padded with `-9999` slots past the latest reading) |
| Response | `Content-Type: text/html` but body is JSON `{"info": {...}, "values": [...]}` | same |
| `info` | `name, light, moderate, heavy, veryheavy, count` | `name, normal, alert, warning, danger, count` (+ `QueryCnt` on the 7-day endpoint) |
| `values` fields | `dt, raw, clean, chourly, cdaily, tdaily, cyearly, c15min` (JSON numbers) | `dt, clean, raw, ecm, final, severity` (JSON strings) |
| Empty range | Non-JSON body `{"count":},]}No result` (24 B) | same |
| Timezone | `dt` has no offset or zone label. Unspecified; consistent with Asia/Kuala_Lumpur (see below) | same |
| Auth / rate limit | None observed | None observed |
| Max range / row limit | 30-day window returned 8,631 rows (8,641 slots, 10 absent): no truncation. > 31 days not tested (tool cap) | 30-day window returned all 8,641 rows: no truncation |
| Pagination | None | None |

## Depth probes

One-day windows (00:00 → next day 00:00, `datafreq=5`). "No result" = the empty-range body.
Bisection was stopped after two steps; boundaries are brackets, not exact dates.

| Sensor | ID | Data found at | "No result" at | Earliest confirmed |
|---|---|---|---|---|
| RF | 27608 | 2024-09-01, 2024-09-24, 2026-06-26, 2026-08-25, 2026-09-18 (2025-09-24 and 2026-03-24: rows returned but 100 % `-9999`) | 2024-08-01, 2024-05-12, 2024-01-01, 2023-01-01, 2022-01-01, 2020-01-01, 2018-01-01 | **2024-09-01** (boundary between 2024-08-02 and 2024-09-01) |
| RF | 25965 | 2024-01-01, 2024-08-01, 2024-09-01, 2025-09-24, 2026-09-18 | 2023-07-02, 2023-01-01, 2020-01-01 | **2024-01-01** (boundary between 2023-07-03 and 2024-01-01) |
| RF | 27661, 27672 | 2024-09-01, 2025-09-24, 2026-09-18 (27661 also 2026-03-24) | not probed earlier | 2024-09-01; earlier unknown |
| WL | 27608 | 2024-09-01, 2024-09-24 (59 % missing), 2026-06-26, 2026-08-25, 2026-09-18 (2025-09-24 and 2026-03-24: 100 % `-9999`) | 2024-08-01, 2024-05-12, 2024-01-01, 2023-01-01 … 2018-01-01 | **2024-09-01** (boundary between 2024-08-02 and 2024-09-01) |
| WL | 27625 | 2024-09-01, 2025-09-24, 2026-09-18 | 2024-08-01 | **2024-09-01** (boundary between 2024-08-02 and 2024-09-01) |
| WL | 27661 | 2024-09-01, 2025-09-24, 2026-09-18 | not probed earlier | 2024-09-01; earlier unknown |
| WL | 5302004_ | 2026-09-18 | 2024-01-01 | 2026-09-18 (only point probed with data) |
| WL | 26460 | rows returned at 2024-09-01, 2025-09-24, 2026-09-18 but **100 % `-9999`**; valid readings only on 2026-09-23 12:25–15:15 | — | no valid history confirmed |

**Summary:** rainfall confirmed back to at least **2024-01-01** (1 of 4 stations) and **2024-09-01**
(3 of 4); water level confirmed back to at least **2024-09-01** (3 of 5). For 27608 (RF and WL) and
27625 (WL) the start of stored data falls in **August 2024**. Earlier data is not served for any
probed station. Whether older data exists anywhere else is unknown.

## Per-station discovery table

Why each station was sampled:
- RF 27608: Timur Laut; display ID duplicated (`1910111RF`); site shared with WL.
- RF 27661: Seberang Perai Utara; shared with WL.
- RF 27672: Barat Daya; `stale` in the inventory.
- RF 25965: Seberang Perai Selatan; 7-digit/"(RHN)" style (`5204049`), a different naming family.
- WL 27608: Timur Laut, Sungai Pinang basin; shared with RF.
- WL 27661: SPU, Sungai Muda basin; shared with RF.
- WL 27625: SPT, Sungai Perai basin; not shared.
- WL 26460: SPS, Sungai Kerian basin; not shared; `stale` in the inventory.
- WL 5302004_: Timur Laut; code-style ID; not shared.

Rows / missing counts are per window. Missing = primary field (`clean` RF, `final` WL) is `-9999`,
blank or null. "Days w/ obs" counts dates with ≥ 1 valid reading; 1-day windows span two dates
because the end is inclusive. No duplicate timestamps and no out-of-order rows occurred in any window.

| Sensor | ID | Window (`from` date, `datafreq`) | Rows | First / last `dt` | Dominant interval | Missing (%) | Largest gap (min) | Days w/ obs | Severity counts |
|---|---|---|---|---|---|---|---|---|---|
| RF | 27608 | 2026-09-18, 5 | 289 | 18/09/2026 00:00 / 19/09/2026 00:00 | 5 | 0 (0) | 5 | 2 | — |
| RF | 27608 | 2026-08-25, 5 | 289 | full day | 5 | 0 (0) | 5 | 2 | — |
| RF | 27608 | 2026-06-26, 5 | 289 | full day | 5 | 0 (0) | 5 | 2 | — |
| RF | 27608 | 2026-03-24, 5 | 289 | full day | 5 | 289 (100) | 5 | 0 | — |
| RF | 27608 | 2025-09-24, 5 | 289 | full day | 5 | 289 (100) | 5 | 0 | — |
| RF | 27608 | 2024-09-24, 5 | 289 | full day | 5 | 0 (0) | 5 | 2 | — |
| RF | 27608 | 2024-09-01, 5 | 289 | full day | 5 | 0 (0) | 5 | 2 | — |
| RF | 27661 | 2026-08-19 → 09-18 (30 d), 5 | 8,631 | 19/08/2026 00:00 / 18/09/2026 00:00 | 5 | 0 (0); 10 slots absent | 25 | 31 | — |
| RF | 27661 | 2026-09-18 / 2026-03-24 / 2025-09-24 / 2024-09-01, 5 | 289 each | full days | 5 | 0 (0) | 5 | 2 | — |
| RF | 27672 | 2026-09-18, 5 | 155 | 18/09/2026 00:00 / 18/09/2026 22:00 | 5 (2.6 % irregular) | 0 (0); 134 slots absent | 480 (after 00:00) | 1 | — |
| RF | 27672 | 2025-09-24 / 2024-09-01, 5 | 289 each | full days | 5 | 0 (0) | 5 | 2 | — |
| RF | 25965 | 2026-09-18 / 2025-09-24 / 2024-09-01 / 2024-08-01, 5 | 289 each | full days | 5 | 0 (0) | 5 | 2 | — |
| RF | 25965 | 2024-01-01, 5 | 289 | full day | 5 | 1 (0.35) | 5 | 2 | — |
| WL | 27608 | 2026-09-18, 5 and 15 | 289 each | full day | 5 | 0 (0) | 5 | 2 | SL_NML 289 |
| WL | 27608 | 2026-08-25 / 2026-06-26 / 2024-09-01, 5 | 289 each | full days | 5 | 0 (0) | 5 | 2 | SL_NML 289 |
| WL | 27608 | 2026-03-24 / 2025-09-24, 5 | 289 each | full days | 5 | 289 (100) | 5 | 0 | blank 289 |
| WL | 27608 | 2024-09-24, 5 | 289 | full day | 5 | 170 (58.8) | 5 | 2 | ERROR 167, SL_NML 119, blank 3 |
| WL | 27661 | 2026-08-19 → 09-18 (30 d), 5 | 8,641 | 19/08/2026 00:00 / 18/09/2026 00:00 | 5 | 6 (0.07) | 5 | 31 | SL_NML 8,632, blank 9 |
| WL | 27661 | 2026-09-18 / 2025-09-24, 5 | 289 each | full days | 5 | 0 (0) | 5 | 2 | SL_NML 289 |
| WL | 27661 | 2024-09-01, 5 | 289 | full day | 5 | 0 (0) | 5 | 2 | ERROR 289 |
| WL | 27625 | 2026-09-18, 5 | 289 | full day | 5 | 1 (0.35) | 5 | 2 | SL_NML 288, blank 1 |
| WL | 27625 | 2025-09-24, 5 | 289 | full day | 5 | 0 (0) | 5 | 2 | SL_NML 289 |
| WL | 27625 | 2024-09-01, 5 | 289 | full day | 5 | 0 (0) | 5 | 2 | ERROR 289 |
| WL | 26460 | 2026-09-23, 5 | 289 | full day | 5 | 254 (87.9) | 5 | 1 | blank 254, SL_NML 35 |
| WL | 26460 | 2026-09-18 / 2025-09-24 / 2024-09-01, 5 | 289 each | full days | 5 | 289 (100) | 5 | 0 | blank 289 |
| WL | 5302004_ | 2026-09-18, 5 | 289 | full day | 5 | 0 (0) | 5 | 2 | SL_NML 289 |

"No result" windows are listed in the depth table above (0 rows).

## Rainfall

- **Endpoint / identifier:** see Mechanism; `jps_internal_id`.
- **Depth:** ≥ 2024-01-01 (25965), ≥ 2024-09-01 (27608, 27661, 27672); nothing served before August 2024 (27608) / July 2023 (25965).
- **Interval:** 5 min in every window (0 % irregular except 27672 on 18/09/2026: 2.6 %).
- **Missing representation (all observed):** (a) rows present with `-9999` in `raw, clean, chourly, cdaily, cyearly, c15min` (`tdaily` stays `0`); (b) rows **absent** from the 5-min grid (27672: 8 h hole; 27661: 10 slots in 30 days); (c) "No result" body for whole ranges. Blank/null not observed. Zero rainfall is `0`, distinct from `-9999`.
- **Units:** mm, from official labels: graph-page table headers "Data Cerapan (mm)", "Data Hujan (mm)", "Kumulatif Harian (mm)", "Kumulatif Tahunan (mm)" and axis "Hujan (mm)".
- **Semantics** (checked on consecutive valid 5-min pairs across all data windows):
  - `raw` = rainfall in the 5-min interval ending at `dt`: `raw` equals the step in `cyearly` in every checked pair (e.g. 288/288 per day, 8,623/8,623 over 30 days). **High confidence.**
  - `cdaily` = running daily total. The 00:00 row still carries the previous day's total; it resets at 00:05. Evidence: 27608, 19/09/2026 00:00 `cdaily` = 38 = sum of `raw` over 18/09 00:05–19/09 00:00, and equal to the listing's published 18/09 daily total (38.0). `cdaily` = previous + `raw` held in all checked pairs except one window (27672, 2025-09-24: 271/287, unexplained). **High confidence for the day boundary; medium overall.**
  - `cyearly` = running yearly total. **High confidence** (monotonic, steps = `raw`).
  - `clean` depends on the request's `datafreq`: at 5, `clean` = `raw` step (288/288); at 15 (and on the 3-day default endpoint), `clean` = trailing 15-min sum of `raw` (287/287, 880/880). The page footnote says "Data Hujan (mm) = Kumulatif Tahunan (mm) - Kumulatif Tahunan (mm) Sebelum". **Use `raw`/`cyearly`, not `clean`, unless `datafreq` is fixed and recorded.**
  - `chourly`, `c15min` equalled `clean` in inspected rows (not hourly/15-min sums at `datafreq=5`); `tdaily` was `0` in every inspected row. **Meaning unknown.**
- **Thresholds:** `info.light/moderate/heavy/veryheavy` = 10/30/60/90 for sampled stations; their unit/period is not labelled (unknown).
- **Limitations:** 4 stations sampled; single-day windows; boundaries bracketed, not exact.

## Water Level

- **Endpoint / identifier:** see Mechanism; `jps_internal_id`.
- **Depth:** ≥ 2024-09-01 (27608, 27625, 27661); nothing before August 2024 for 27608/27625;
  5302004_ has nothing at 2024-01-01; 26460 returns rows but no valid reading in 3 of 4 windows.
- **Interval:** 5 min in every window, 0 % irregular, no absent rows observed (the grid is padded).
- **Missing representation (observed):** (a) `clean, ecm, final` (and usually `raw`) = `-9999` with `severity` blank; (b) `raw` present but `clean/ecm/final` = `-9999` with `severity` = `ERROR` (27608, 24/09/2024: e.g. `raw` 23.11–23.13, above the published danger level 21.5); (c) "No result" body; (d) the 7-day default endpoint pads future slots with `-9999`. `severity` = `ERROR` also occurs with valid `final` values (27661, 27625 on 2024-09-01, whole day). Blank/null values not observed.
- **Units:** metres, from official labels: table headers "Data Aras Air (m) - Raw / ECM / Clean", axis "Aras Air (m)". **Threshold unit is metres:** the page JS tooltip prints "Normal: …m Waspada: …m Amaran: …m Bahaya: …m".
- **Fields:** `raw`, `ecm`, `clean`, `final` are strings; the page plots `final`. What ECM means is not documented.
- **Severity codes observed:** `SL_NML`, `SL_ALT` (7-day endpoint, 27587), `ERROR`, blank. Other codes unknown.
- **Thresholds with history:** every response's `info` carries `normal/alert/warning/danger`. The values returned for 2024 windows equal the current listing values (27608: 0/21/21.2/21.5), so they appear to be *current* thresholds, not time-versioned. Whether thresholds changed historically is unknown.
- **Limitations:** 5 sites sampled; single-day windows; boundaries bracketed.

## Cross-Sensor Alignment

Metadata comparison only; nothing merged.

- **27608** (Kolam Takungan Sg. Dondang M/S): RF and WL on 18/09/2026 both returned 289 rows on the identical 5-min grid (00:00 … 00:00). Both are 100 % `-9999` on the same two sampled days (2025-09-24, 2026-03-24), and both start after 2024-08-01. The outages coincide, but the cause is unknown.
- **27661** (Bumbung Lima): over 19/08–18/09/2026, RF had 8,631 rows (10 grid slots absent, max gap 25 min) and WL had 8,641 rows (6 `-9999`). Timestamps are on the same 5-min grid, so they can be aligned by `dt` with explicit handling of absent RF slots and WL `-9999`.
- **Overlap:** confirmed in every sampled window from 2024-09-01 to 2026-09-18 for 27661, and in 5 of 7 windows for 27608.

## ML Feasibility

| Sensor | Assessment | Evidence | Main unknowns |
|---|---|---|---|
| Rainfall | **PARTIAL** | 5-min cadence; raw/daily/yearly semantics established. ≥ 2024-01-01 (1 station) / ≥ 2024-09-01 (3 stations), i.e. about 2–2.7 years. Gaps: whole days of `-9999`, absent rows | Station coverage beyond the 4 sampled; exact start dates; long-gap frequency; completeness over full months; data before 2023 (not served) |
| Water level | **PARTIAL** | 5-min cadence; metre unit and thresholds confirmed. ≥ 2024-09-01 (3 of 5 sites), about 2 years. Per-reading severity available. Some sites mostly `-9999` (26460). QC `ERROR` periods | Per-site completeness; meaning of `ERROR`/ECM; whether thresholds are historical |

- **Flood / threshold event counts are unmeasured.** Only the small counts above were seen (e.g. 19 `SL_ALT` readings in one 7-day sample for 27587). No labels were built.
- **Risk to ADR-0004** ("years of labeled history"): the depth served here is about 2 years for most probed sites. The ADR is **not** edited. It says to revisit if depth is insufficient; that decision needs full-coverage and event-count measurement, plus the data.gov.my check (separate task).

## Timezone

No response states a timezone or offset. Evidence of consistency with Asia/Kuala_Lumpur:
- 26460's last valid history reading (23/09/2026 15:15) equals the listing's "Kemaskini Terakhir" for that station.
- The 7-day endpoint fetched at ~01:56 +08:00 had its last valid reading at 24/09/2026 01:45 and padded slots up to 02:10.

Recorded as **"source timezone unspecified; consistent with Asia/Kuala_Lumpur"**.

## Unknowns

- Exact archive start per station (bracketed only) and whether other stations go deeper.
- Server behaviour for windows > 31 days (not tested by design).
- Meaning of `tdaily`, `chourly`, `c15min`, ECM, `ERROR`, and full severity code list.
- Whether thresholds are historical or current-only.
- Licensing/terms for automated historical retrieval (separate Phase 1 task).

## Reproduce one probe

```text
.venv\Scripts\python.exe scripts\probe_jps_history.py rainfall 27608 2026-09-18 2026-09-19
.venv\Scripts\python.exe scripts\probe_jps_history.py water_level 27661 2026-08-19 2026-09-18 --allow-wide
```

Exit codes: `0` ok (including "No result" → `info.fg_no_result = "true"`, 0 rows), `2` schema change,
`3` fetch failure (includes HTTP 403/429; do not retry), `4` request rejected by the window guard.
