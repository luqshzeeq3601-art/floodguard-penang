# JPS Public Infobanjir — Pulau Pinang Station Inventories

Discovery metadata (versioned; not raw pipeline data). Two **separate** inventories, not merged:

| File | Script | Rows | Committed run (Asia/Kuala_Lumpur) |
|---|---|---|---|
| `penang_rainfall_stations.csv` | `scripts/discover_jps_rainfall_stations.py` | 56 | `2026-09-24T01:57:44+08:00` |
| `penang_water_level_stations.csv` | `scripts/discover_jps_water_level_stations.py` | 22 | `2026-09-24T02:01:23+08:00` |

Raw evidence (response bodies byte-for-byte as received, UTF-8, LF):
`raw/searchresultrainfall_PNG_20260924T015744+0800.html` (31,378 B = `Content-Length`),
`raw/aras-air-data_PNG_20260924T020123+0800.html` (20,354 B).

Shared code: `scripts/_jps_common.py` (fetch, state-page parser, result-table parser, freshness
rule, CSV writer). Both CSVs are sorted by `jps_internal_id`.

## Column naming convention

| Prefix / name | Meaning |
|---|---|
| `jps_internal_id` | `stationid` query parameter of the row's graph link (`/index.php/rf-graph/?stationid=…` or `/index.php/wl-graph/?stationid=…`), verbatim (one rainfall value has a leading space: `" 5402002_"`). Site-internal; unique within each inventory in every run observed. **Not** a canonical FloodGuard `station_id`. |
| `jps_display_station_id` | "ID Stesen" cell, verbatim. Not unique and not always present. |
| no prefix | Other fields copied verbatim from the source (`station_name`, `district`, basin, levels, thresholds) or constant (`state`, `source_url`). |
| `fg_…` | **FloodGuard-derived**, not published by JPS. |

### FloodGuard-derived fields

| Column | Rule |
|---|---|
| `fg_display_station_id_flag` | `ok`; `duplicate` (same display ID on >1 row of the same inventory); `missing` (empty cell); `no_data_text` (cell reads "No Data"). |
| `fg_freshness_minutes` | Newest `latest_observation_time` in the same response minus this row's, in whole minutes. Relative to the source, so no clock or timezone assumption. |
| `fg_freshness_status` | `stale` if `fg_freshness_minutes` > **180** (`FG_STALE_AFTER_MINUTES` in `scripts/_jps_common.py`, the only definition), else `reporting`. Provisional inventory rule; JPS publishes no online/offline field in either listing. |
| `fg_threshold_order_flag` (water level) | `ok` if Waspada ≤ Amaran ≤ Bahaya; `not_ascending` otherwise; `missing` if any of the three is blank. Values are never repaired. "Normal" is not checked (see below). |

`latest_observation_time` is the "Kemaskini Terakhir" cell converted to ISO **without offset**:
the source declares no timezone. Values are consistent with Malaysia local time (never later
than HTTP `Date` + 8 h in any capture) but that is an observation, not a JPS statement.

## Access mechanism (verified 2026-09-24)

robots.txt: `User-agent: *`, `Disallow: /wp-admin/`, `Allow: /wp-admin/admin-ajax.php`; the
paths below are not disallowed. Scripts send 2 GETs per run, 2 s apart, UA
`FloodGuard-Penang-discovery/0.1 (research)`. Both endpoints were confirmed in the browser
network log as the requests the official pages issue.

| Aspect | Rainfall ("Data Hujan") | Water level ("Data Aras Air Sungai") |
|---|---|---|
| State page | `/hujan/data-hujan/?state=PNG&type=NEGERI` | `/aras-air/data-paras-air/?state=PNG&type=NEGERI` |
| Data endpoint | `/wp-content/themes/shapely/agency/searchresultrainfall.php?state=PNG&district=ALL&station=ALL&loginStatus=0&language=0` | `/index.php/aras-air/data-paras-air/aras-air-data/?state=PNG&district=ALL&station=ALL` (served at the same path without `/index.php`) |
| Documented? | No — site-internal XHR of a WordPress theme | No — site-internal XHR (a commented-out older `searchresultwaterlevel.php` call is still in the page JS) |
| Method / format | GET; `text/html` table fragment | GET; `text/html` table fragment |
| Auth / CAPTCHA | None (`loginStatus=0`) / none | None / none |
| Pagination | None | None |
| Filters | `state`, `district` (`ALL` or name), `station` (`ALL` or id), `language` (0 = Malay) | `state`, `district`, `station`; page JS also passes `type=MOCKUP` for a test view (not used) |
| Update behaviour | Not published. Newest row time 01:15 (01:39 capture) → 01:30 (01:44/01:45 runs) → 01:45 (01:57 run). | Not published. 16/22 rows at 01:45 in both runs (01:57 and 02:01); others 01:00–01:25 and one 23/09 15:15. |
| Server download | None (client-side TableExport JS only) | None found |
| Markup quirks | Data rows lack opening `<tr>`; rows split on `<td data-th='No'>` | Proper `<tr class='item'>` rows; `data-th` labels say "Main Basin (mm)" / "Sub River Basin (mm)" although the cells hold basin names |

Page footer "Kemaskini Terakhir" (page-level) read `24/09/2026 01:45` at HTTP `Date` 17:39 GMT and
`02:00` at ~01:57 local, i.e. ahead of the server clock; its meaning is undocumented and not used.

## Rainfall inventory — `penang_rainfall_stations.csv`

Columns: `jps_internal_id, jps_display_station_id, fg_display_station_id_flag, station_name,
state, district, latest_observation_time, fg_freshness_minutes, fg_freshness_status, source_row,
source_url, discovered_at`. Rainfall values (6 daily totals, since-midnight, latest 1 h) are in the
response but not copied (volatile observations); they remain in the raw evidence.

Results (run 01:57:44): 56 rows, 56 unique `jps_internal_id`; reporting 52, stale 4
(`27672` Tali Air Besar Sg. Pinang (F2) 630 min, `27616` Pejabat Pertanian Cherok Tok Kun (F2)
465, `27648` Permatang Pak Elong (F2) 435, `27643` Bakar Kapor (F2) 225); newest row 24/09/2026 01:45.
Districts: Seberang Perai Utara 19, Timur Laut Pulau Pinang 12, Seberang Perai Tengah 9, Barat Daya
Pulau Pinang 8, Seberang Perai Selatan 8. Display-ID flags: ok 49, duplicate 4 (`1910111RF` ×2 —
Kolam Bersih (F2) and Kolam Takungan Sg. Dondang M/S (F2); `0000000RF` ×2 — Cherok Tok Kun and
Pejabat JPS SPU), missing 1 (`26186` Permatang Tok Jaya), `No Data` 2. Not in source: coordinates,
basin/river, thresholds, status.

## Water-level inventory — `penang_water_level_stations.csv`

Columns: `jps_internal_id, jps_display_station_id, fg_display_station_id_flag, station_name,
state, district, main_basin` ("Lembangan"), `sub_river_basin` ("Sub Lembangan"),
`latest_observation_time, water_level_m` ("Aras Air (m)", text as published),
`threshold_normal, threshold_alert, threshold_warning, threshold_danger` (group "Tahap Nilai
Ambang": Normal / Waspada / Amaran / Bahaya, text as published), `fg_threshold_order_flag,
fg_freshness_minutes, fg_freshness_status, source_row, source_url, discovered_at`.

Threshold units: the threshold headers carry **no unit label**. They sit beside the "Aras Air (m)"
column and, for the one station sampled (`27587`), equal the `info.normal/alert/warning/danger`
values in the graph JSON (4 / 5.2 / 5.5 / 6). The metre unit is therefore likely but not stated,
so column names carry no `_m` suffix.

Results (run 02:01:23): 22 rows, 22 unique `jps_internal_id`; reporting 21, stale 1 (`26460`
Sg. Kerian di Sri Sanglang (F2), 23/09/2026 15:15, 630 min); newest row 24/09/2026 01:45.

- Districts: Timur Laut Pulau Pinang 9, Seberang Perai Utara 7, Seberang Perai Selatan 3,
  Seberang Perai Tengah 2, Barat Daya Pulau Pinang 1.
- Display IDs: 21 `ok`, 1 `No Data` (`26189`); no duplicates, no blanks.
- Thresholds: all four present on all 22 rows (none missing); `fg_threshold_order_flag` = `ok` for 22
  (no ordering exceptions). Each row has its own thresholds (no single Penang threshold).
- "Normal" is `0.00` on 14/22 rows; on 3 rows it exceeds the current level (`26460` 2.00 vs 0.09,
  `5302004_` 19.50 vs 19.25, `5403043_` 0.45 vs 0.00). Its semantics are undocumented, so it is not
  validated. `5403043_` reports level `0.00`; whether that is a real reading is unknown.
- Basin fields present on all rows (10 distinct main basins; Sungai Pinang 8, Sungai Perai 4).
- **Unavailable (dropped, empty for every row):** trend (no trend text, icon, image or CSS class in
  the listing), official status/severity text, coordinates (none in listing, wl-graph page or its
  JS). Official per-reading severity codes exist only in the graph JSON (below).

## Run-to-run validation

- Rainfall: runs at 01:44:00 and 01:45:36 — identical 56 IDs and all fields except `discovered_at`.
  The 01:57:44 regeneration (after the column rename) has the same 56 `jps_internal_id`s and
  display-ID multiset; only times/freshness changed.
- Water level: runs at 01:57:49 and 02:01:23 — identical 22 IDs, display IDs, and every field except
  `discovered_at` (no level or time changed in those 3.5 min). An earlier manual capture (01:53)
  showed `26189` at 01:00 with level 2.11; both runs show 01:15 and 2.10, so values are volatile.
- Checks passed for both: unique non-empty `jps_internal_id`, non-empty names, `state = Pulau
  Pinang`, districts in the page's official list, timestamps parse, numeric fields numeric, no
  duplicate rows, `source_url`/`discovered_at` on every row.

## Cross-check rainfall vs water level (metadata only; nothing merged)

- `jps_internal_id` overlap: **13** of 22 water-level IDs also appear in the rainfall inventory
  (27587, 27608, 27612, 27613, 27620, 27628, 27647, 27661, 27663, 26189, `5403043_`,
  `BUMBUNGLIMA`, `LIMBUNGAN`), each in the same district. The same graph key is used by both
  `rf-graph` and `wl-graph`; whether it denotes one physical site is not stated by JPS.
- Exact name overlap: 4 — "Kolam Takungan Sg. Dondang M/S (F2)", "Muara Sg. Pinang S18 (F2)",
  "Sg.Muda di Bumbung Lima", "Rumah Pam Taman Limbungan".
- Near-name (rainfall name contained in water-level name after removing "(F2)/(RHN)" and
  punctuation, same district), beyond shared IDs: WL `27667` Sg. Lahar Endin di Pejabat JPS SPU (F2)
  ↔ RF `27666` Pejabat JPS SPU (F2); WL `27661` Sg. Muda di Bumbung Lima (F2) ↔ RF `BUMBUNGLIMA`;
  WL `BUMBUNGLIMA` ↔ RF `27661` Bumbung Lima (F2).
- Display-ID overlap: exact `5403444` (Rumah Pam Taman Limbungan) and the text "No Data". Ignoring
  the `RF`/`WL` suffix, 9 "(F2)" display IDs match (e.g. `1910131WL` ↔ `1910131RF`); `1910111WL`
  (Dondang M/S) matches rainfall `1910111RF`, which JPS shows on two rainfall rows.
- Colocation candidates = the shared-ID and near-name pairs above; unverified, no coordinates exist
  to confirm.

## Historical access

Verified 2026-09-24. Full findings: [`HISTORICAL_AVAILABILITY.md`](HISTORICAL_AVAILABILITY.md); probe tool: `scripts/probe_jps_history.py`.

- Date-range endpoints (site-internal, unauthenticated GET, JSON body):
  `searchresultrainfalldthourlylead.php` for rainfall and `searchresultwaterleveldtlead.php` for water
  level. Parameters are `station=<jps_internal_id>` and `from`/`to` as `DD/MM/YYYY HH:mm` (inclusive).
- Rows every 5 min. A 30-day window was returned in full; no pagination.
- **Depth:** confirmed back to at least 2024-01-01 (1 rainfall station) and 2024-09-01 (3 rainfall and
  3 water-level sites). Ranges before about August 2024 (or July 2023 for station 25965) return
  `No result`.
- **Missing values:** `-9999`, rows absent from the grid (rainfall), and blank or `ERROR` severity
  (water level). Zero rainfall is `0`.
- **Units:** rainfall in mm and water level in m. Water-level thresholds are in m (official graph-page
  JS). Timestamps carry no timezone.

## Live access

Verified 2026-09-24. Full findings: [`LIVE_ACCESS.md`](LIVE_ACCESS.md); one-shot probe: `scripts/probe_jps_live.py`.

- The state listings (2 requests cover all 78 Penang rows) are the recommended live source.
- They send no ETag/Last-Modified and ignore conditional requests.
- "(F2)" stations publish every 15 min, in sync, 4–7 min after the observation time. Other
  stations publish asynchronously, 10–30 min apart, with lag up to ~57 min.
- Recommended polling interval: 5 min.
- `fg_live_status` (FRESH/DELAYED/STALE/NO_DATA/INVALID) is defined in `scripts/_jps_common.py`.

## Limitations

- Undocumented site-internal endpoints; markup/params can change without notice. Scripts exit `2`
  with `SCHEMA CHANGE: …` on header, cell-count, district, state, internal-ID, time-format or
  numeric-format changes; `3` on network failure.
- `jps_internal_id` uniqueness is observed, not guaranteed; `jps_display_station_id` is unreliable.
- One night's snapshots only; offline stations may disappear from listings rather than go stale.
- Licensing/terms of use not reviewed (separate Phase 1 task).

## Reproduce

```text
.venv\Scripts\python.exe scripts\discover_jps_rainfall_stations.py --save-raw
.venv\Scripts\python.exe scripts\discover_jps_water_level_stations.py --save-raw
.venv\Scripts\python.exe -m pytest tests\test_discover_jps_rainfall_stations.py tests\test_discover_jps_water_level_stations.py
```

Options: `--output PATH`, `--raw-dir PATH`. Tests are offline and use trimmed real captures in
`tests/fixtures/jps/`.
