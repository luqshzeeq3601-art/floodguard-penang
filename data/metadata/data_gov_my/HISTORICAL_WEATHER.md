# data.gov.my — Historical Weather / Climate Coverage (Pulau Pinang)

Verified 2026-09-24, 03:49–03:57 UTC (11:49–11:57 +08:00). Discovery only: no ingestion, tables,
features or labels were built. 25 unauthenticated sequential `GET`/`HEAD` requests, UA
`FloodGuard-Penang-discovery/0.1 (research)`, at least 5 s apart and 16 s apart for scripted calls
(4 of them via `curl`, 21 via Python `urllib`, logged in `raw/probe_log_20260924.tsv`). No 429, 403 or
CAPTCHA. The largest file transferred was 671 KB (the catalogue page). No archive or parquet was downloaded.

Evidence labels: **[probe]** seen in a live response this session; **[doc]** read from official
documentation or metadata fetched live; **[inferred]** reasoned from probe evidence;
**[not verified]** could not be checked.

## 1. Answer

**data.gov.my has no historical weather observation dataset usable as short-horizon training
context for FloodGuard v1.**

- The open data catalogue (292 datasets, 45 source agencies) contains **no dataset from
  METMalaysia or JPS**. Neither agency appears in the catalogue's source list. There is also no rainfall,
  temperature, humidity, pressure, wind or water-level dataset [probe]. Catalogue searches for
  `rainfall` and `hujan` return 0 datasets, and `api.data.gov.my/data-catalogue?id=rainfall` returns 404
  "does not exist" [probe].
- The developer portal lists exactly three real-time APIs: Weather (forecast/warning, already
  assessed in `data/metadata/metmalaysia/ACCESS.md`, no archive), GTFS Static and GTFS Realtime
  [probe]. No historical weather API is documented.
- The only historical weather data on data.gov.my is the **"Weather and Climate" dashboard**
  (METMalaysia manned stations, **daily** rainfall total and mean temperature). It includes
  **Bayan Lepas and Butterworth** but is **frozen at 2022-12-31**, with daily data covering only
  2020-12-31 → 2022-12-31. That period **does not overlap** the JPS 5-min history (2024-01/09 onward).
- OpenDOSM (183 datasets) holds nothing weather-related beyond the same national air-pollution
  and river-basin tables [probe].

## 2. Candidates

### A. "Weather and Climate" dashboard: `data.gov.my/dashboard/weather-and-climate/<slug>`

| Field | Finding |
|---|---|
| Access layer vs publisher | data.gov.my dashboard (catalogue/visualisation layer). Metadata `agency: "Met"`. The page says data comes from "the 42 manned weather stations operated by the Malaysian Meteorological Department" [probe] |
| Catalogue entry / API | **None.** The dashboard is not a data-catalogue dataset and has no documented API. Data is embedded in the Next.js page (`__NEXT_DATA__.props.pageProps`) [probe]. Chart sources per the official `data-gov-my/datagovmy-meta` repo (`dashboards/weather_and_climate.json`): `storage.data.gov.my/dashboards/weather_station.parquet` (4,519 B), `weather_station_timeseries.parquet` (407,028 B), `weather_station_timeseries_callout.parquet`. HEAD `Last-Modified` for the two probed files is 30 Aug 2023 07:16:24–25 GMT [probe]. There is no CSV sibling (`…timeseries.csv` → 404) [probe]. Parquet was **not downloaded or read** (no pyarrow in `.venv`) |
| Auth / licence | No auth [probe]. Licence: data.gov.my FAQ states CC BY 4.0 for open data [doc, via ACCESS.md]. Whether that covers dashboard-only data is [not verified] |
| Update frequency | `last_updated 2023-06-30 12:00`, `data_as_of 2022-12-31 23:59`, `next_update: null` [probe]. **Not maintained.** |
| Geography | 42 stations nationally, each with `station`, `lat`, `lon`, `slug` (officially provided) [probe]. No WMO/MET station ID is published. Matching to `/projection/rain` IDs 48601/48602 is **not asserted** |
| Penang | `Bayan Lepas, Pulau Pinang` (5.297222, 100.272222, `bayan-lepas`); `Butterworth, Pulau Pinang` (5.457222, 100.388333, `butterworth`) [probe] |
| Fields / units | `x` (epoch ms), `rainfall`, `temperature`. The UI labels them "Total Rainfall" and "Mean Temperature" [probe]. The units mm and °C are [inferred] (not stated on the page). Values are floats, e.g. `2.8800000000000003` |
| Series | `daily` (731), `daily_7d` (731, a **trailing** 7-day mean; checked, max abs error vs trailing mean < 1e-13, centred ≥ 18.6), `monthly` (120), `yearly` (10) [probe] |
| Date range | daily/daily_7d **2020-12-31 → 2022-12-31**; monthly 2013-01 → 2022-12; yearly 2013 → 2022 (both stations) [probe] |
| Timestamps | `x` is 00:00 **UTC** of the labelled date (e.g. `1609372800000` = 2020-12-31T00:00Z) [probe]. This is a date label. The climatological day boundary (MYT midnight, 00 UTC, 08 MYT, …) is **unspecified** [not verified]. Asia/Kuala_Lumpur is **not** assumed |
| Missing values | 0 nulls/NaN in every series for both stations [probe]. The page note says observations "are recorded manually on the rare occasions when automation does not operate as intended" [probe]. Whether gaps were filled is [not verified]. Zero rainfall is a published value and is kept as a measurement |
| Consistency | Monthly rainfall equals the sum of daily values (2021-01..04, both stations) [probe] |
| Classification | **Actual historical observation (daily aggregate)**, plus derived climatological summaries (monthly/yearly) |

Probe metrics (daily series):

| Station | Rows | Range | Interval | Duplicates | Gaps | Nulls | Zero-rain days | Max daily rain | Temp range |
|---|---|---|---|---|---|---|---|---|---|
| Bayan Lepas | 731 | 2020-12-31 → 2022-12-31 | 1 day (only) | 0 | 0 | 0 | 262 | 97.07 | 25.09–30.54 |
| Butterworth | 731 | 2020-12-31 → 2022-12-31 | 1 day (only) | 0 | 0 | 0 | 301 | 93.03 | 24.50–29.97 |

Monthly/yearly: 120/10 rows per station, no nulls; Bayan Lepas yearly totals range 1,745.0–3,047.3,
Butterworth 1,988.0–2,741.5 (2013–2022).

### B. `air_pollution`: Monthly Air Pollution (catalogue, JAS/DOSM)

`api.data.gov.my/data-catalogue?id=air_pollution` [probe], CSV `storage.data.gov.my/environment/air_pollution.csv`
(9,299 B, HEAD). Monthly, **national** (no state/station field), 6 pollutants, 2017-01 → 2022-12
(`sort=-date` → 2022-12-01) [probe]. Nulls documented for 2017. `next_update 2024-11-27` has passed
without an update. **Classification:** climatological summary, not weather.

### C. `water_pollution_basin` (JAS)

Annual share of river basins by pollution class, `data_as_of 2021` [probe, catalogue]. Water quality,
not hydrology. Not probed further.

### D. data.gov.my Weather API (`/weather/forecast`, `/weather/warning`)

Already verified in `data/metadata/metmalaysia/ACCESS.md`: current forecast and warnings only, no
archive, no forecast issue time. Not re-probed.

### E. Linked agency sources (not data.gov.my datasets)

- METMalaysia myMETdata: historical station data, fee-based and behind login (per ACCESS.md). Not probed.
- DOE APIMS (`eqms.doe.gov.my/APIMS/main`): 200, 4,659 B JavaScript shell [probe]. Station content,
  history and terms are [not verified]. Not linked from the data.gov.my catalogue.
- `data.gov.my/dashboard/flood-warning`: 404 in both `en` and `ms-MY` [probe], although the route
  name is listed in the dashboard JS bundle. No flood-warning dashboard is live.

## 3. Classification for FloodGuard v1

| Candidate | Class | vs JPS historical | Reason |
|---|---|---|---|
| A. Weather & Climate dashboard, daily | **NOT SUITABLE** (model features) | Cannot be aligned safely: no time overlap | Daily resolution, frozen 2022-12-31, 2 gauges; JPS history starts 2024 |
| A. Weather & Climate dashboard, monthly/yearly | **OPTIONAL** (EDA context only) | Coarse context only | 10-yr Penang rainfall seasonality/annual totals for EDA narrative; never a model input |
| B. `air_pollution` | **NOT SUITABLE** | Unrelated | National monthly, no Penang, no flood role |
| C. `water_pollution_basin` | **NOT SUITABLE** | Unrelated | Annual water-quality class |
| D. Weather API | As ACCESS.md (forecast RECOMMENDED live-only) | — | No history |
| E. myMETdata / DOE APIMS | **DEFERRED** / **NOT SUITABLE** | myMETdata might add hourly MET station history; fee-based | APIMS: no flood role |

No probe script was written. No stable, documented, maintained historical endpoint exists. The only
historical series is an unmaintained dashboard payload with no training value for v1.

## 4. Per-variable ML relevance (+30 / +60 / +120 min)

| Variable | Source | Resolution | Penang coverage | Relevance 30/60/120 | Decision |
|---|---|---|---|---|---|
| Rainfall | Dashboard A | Daily total | 2 stations, 2021–2022 | None / None / None: daily totals can't resolve sub-2 h dynamics; a same-day total also contains rain after the prediction time (leakage) | Not in feature plan |
| Rainfall (antecedent, e.g. prior-day total) | Dashboard A | Daily | 2021–2022 only | Low; JPS 5-min rainfall already yields antecedent totals for the training period | Not in feature plan |
| Temperature (daily mean) | Dashboard A | Daily | 2 stations, 2021–2022 | None | Not in feature plan |
| Humidity, pressure, wind | — | — | **No data.gov.my source** | — | No source |
| Air pollutants | B | Monthly national | None | None | Not in feature plan |
| Water level | — | — | **No data.gov.my source**; JPS only | — | JPS |

## 5. Evidence files (`raw/`)

| File | Content |
|---|---|
| `catalogue_index_20260924T114902+0800.csv` | All 292 catalogue ids with category, source agencies, `data_as_of`, title, parsed from `data.gov.my/data-catalogue` |
| `weather_and_climate_{bayan-lepas,butterworth}_pageProps_trimmed_*.json` | Dashboard `pageProps` without i18n/dropdown; values verbatim |
| `weather_and_climate_stations_20260924T115044+0800.json` | 42-station dropdown (name, lat, lon, slug), verbatim |
| `datagovmy-meta_dashboards_weather_and_climate_*.json` | Official dashboard metadata (chart parquet sources), byte-for-byte |
| `api_data-catalogue_air_pollution_*.json`, `api_data-catalogue_id-rainfall_404_*.json` | API responses, byte-for-byte |
| `probe_log_20260924.tsv` | UTC time, method, status, bytes, URL, key headers for the 21 scripted requests |

Unlogged `curl` requests: `data.gov.my/data-catalogue` 200 (03:49:02Z), `/dashboard` 200
(03:49:47Z), `/dashboard/weather-and-climate` 200 (03:49:58Z), `/dashboard/flood-warning` 404
(03:50:03Z).

## 6. Limitations

- The catalogue listing was read from one page render (292 ids). Datasets flagged
  `exclude_openapi` or unlisted would be missed [not verified].
- The dashboard parquet files (all 42 stations) were not read, for lack of a parquet reader.
  Only the two Penang page payloads were profiled.
- The daily-rainfall day boundary, the units, gap filling and QC are undocumented.
- myMETdata content, price and terms were not checked.
- A CC BY 4.0 licence for dashboard-only data is not explicitly stated.
