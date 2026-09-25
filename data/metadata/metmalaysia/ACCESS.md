# METMalaysia — API / Data Access (Pulau Pinang)

Verified 2026-09-24, 03:28–03:41 UTC (11:28–11:41 +08:00). Discovery only: no ingestion, tables,
features or labels were built. All probes were unauthenticated `GET`s, sequential, UA
`FloodGuard-Penang-discovery/0.1 (research)`, about 65 requests in total (10 to `api.data.gov.my`,
never more than 4 per minute). No 403 or 429 was returned, and no CAPTCHA appeared. Tools: Python
`urllib`, plus `curl` (Windows Schannel) for `api.met.gov.my`, whose TLS chain Python's CA bundle
rejects (`CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain`). Verification was
never disabled.

Evidence labels used below:

- **[probe]**: seen in a live response during this session.
- **[doc]**: read from official documentation pages, which were themselves fetched live.
- **[inferred]**: reasoned from probe evidence, not stated by the source.
- **[not verified]**: could not be checked.

## 1. Sources probed

### A. data.gov.my Weather API: forecast (**RECOMMENDED**, live only)

| Field | Finding |
|---|---|
| Endpoint | `GET https://api.data.gov.my/weather/forecast` [probe] |
| Provenance | "The data is provided by MET Malaysia" (developer.data.gov.my/realtime-api/weather) [doc]. METMalaysia's own Open Data page links to it as an official channel (`met.gov.my/info/data-terbuka`) [probe] |
| Auth / registration | None. HTTP 200 without a token or key [probe] |
| Params | None required. Optional `filter`, `ifilter`, `contains`, `icontains`, `range`, `sort`, `limit`, `include`, `exclude`, `date_start`/`date_end` (`YYYY-MM-DD@column`), `timestamp_start`/`timestamp_end` [doc]. Nested fields use `__`, e.g. `contains=St003@location__location_id` → 7 rows [probe] |
| Rate limit | 4 requests/min for the Weather API; `429 Too Many Requests` when exceeded [doc]. Not triggered [probe] |
| Response | `application/json`, top-level array. Unfiltered: 898,859 B, **3,080 records = 440 locations × 7 dates** (2026-09-24…2026-09-30) [probe]. `Cache-Control: private`, Cloudflare. No `ETag` or `Last-Modified` |
| Record schema | `location{location_id, location_name}`, `date`, `morning_forecast`, `afternoon_forecast`, `night_forecast`, `summary_forecast`, `summary_when`, `min_temp`, `max_temp` [probe] |
| Units | `min_temp`/`max_temp` are integers in °C [doc]; observed 24–32 for Penang [probe]. The four `*_forecast` fields are categorical Malay text, e.g. `Tiada Hujan`, `Hujan di beberapa tempat`, `Ribut petir di kebanyakan tempat`, `Jerebu` (16 distinct values nationally). `summary_when` takes one of 7 values (`Pagi`, `Petang`, `Malam`, `Pagi dan Petang`, `Petang dan Malam`, `Pagi dan Malam`, `Sepanjang Hari`) [probe]. **No quantitative rainfall (mm) and no probability** |
| Temporal resolution | One record per location per calendar day, split into morning, afternoon and night text. The day-part hour boundaries are not documented [not verified] |
| **Issue time** | **Not published**, neither in the API record nor on met.gov.my's per-location forecast pages [probe]. The update cadence is documented only as "updated daily" [doc]. The exact issue hour is [not verified] |
| **Valid time** | Only `date`, a naive calendar date. `Asia/Kuala_Lumpur` is [inferred]: the first date equals the MYT date at retrieval |
| Archive / backfill | **None.** `date_start=2026-09-01@date&date_end=2026-09-23@date` → HTTP 200, `[]` (2 B) [probe]. Only the current 7-day window is served |
| Location IDs | `St` state, `Ds` district, `Tn` town, `Rc` recreation centre, `Dv` division [doc]. IDs are stable in form (`AA000`), and long-term stability is [not verified]. **No state field and no coordinates** in the API |
| Penang coverage | **28 location IDs, 196 rows** per response (`penang_locations.csv`): St003; districts Ds011, Ds012, Ds013, Ds014, Ds017 (all 5 Penang districts); 19 towns; 3 recreation centres. Penang membership comes from the `Pulau Pinang` groups on met.gov.my's forecast selectors, not from the API. All 28 names match the API [probe]. Ds012 values for all 7 days matched `met.gov.my/forecast/weather/district/Ds012` [probe] |
| Licence | "made open under the Creative Commons Attribution 4.0 International License (CC BY 4.0)" (developer.data.gov.my/faq) [doc]. The data.gov.my "Terms of Use" footer link is `#`, so the full terms are [not verified] |
| Automated polling | [inferred] permitted within 4 req/min: an open API with a published rate limit and CC BY 4.0 |
| Stability | Two responses (11:29:26 and 11:40:40 +08:00) had identical Penang rows [probe]. When the day's forecast changes is [not verified] |

### B. data.gov.my Weather API: warning (**OPTIONAL**, live context only)

| Field | Finding |
|---|---|
| Endpoint | `GET https://api.data.gov.my/weather/warning` [probe]. `/weather/warning/earthquake` exists [doc] but is irrelevant to FloodGuard and was not probed |
| Auth / rate limit / licence | Same as A |
| Response | JSON array. **4 records**, 7,962 B, at both 11:29 and 11:40 (JSON-equal; the bytes differ) [probe] |
| Schema | `warning_issue{issued, title_bm, title_en}`, `valid_from`, `valid_to`, `heading_en/bm`, `text_en/bm`, `instruction_en/bm` [probe]. `valid_*` and `instruction_*` can be `null` (the "No Advisory" record) |
| Times | `issued`, `valid_from` and `valid_to` are naive ISO datetimes. **Issue time and valid period are both present** [probe]. MYT is [inferred]: `issued=09:00:00` matches the met.gov.my bulletin "Issued at 9:00 AM" whose `Last-Modified` is 01:04:07 UTC (09:04 MYT), and `issued=10:30:00` matches the "No Advisory" page `Last-Modified` 02:33 UTC |
| Anomalies | 2 of 4 records have `valid_from` **before** `issued` (2026-09-20 and 2026-09-23 vs issued 2026-09-24T09:00). One has `valid_to` = 2026-09-24T00:00, already past at retrieval, and it is still returned [probe]. The meaning is [not verified]. The probe flags `fg_valid_from_before_issued` and keeps the records |
| Types observed | "Strong Winds and Rough Seas Warning" (×3), "No Advisory" (tropical cyclone) [probe]. Warning families on met.gov.my: continuous rain, thunderstorm, strong wind/rough seas, tropical cyclone, earthquake/tsunami [probe]. A continuous-rain or thunderstorm record in this API has **not been observed** |
| Severity terms | Continuous rain criteria page (`/ramalan/hujan-lebat`): `WASPADA` (< 150 mm/24 h), `BURUK` (> 150 mm/24 h), `BAHAYA` (> 250 mm/24 h), with "24 h counted from when rain starts" [probe]. Strong wind/rough seas: "First Category" [probe]. **Not mapped to FloodGuard risk labels** |
| Geographic scope | **Free text only** (e.g. "waters of Phuket", "Southern Straits Of Melaka"). No location IDs, polygons or state codes [probe]. Penang relevance would need text matching. The probe's `fg_mentions_pulau_pinang` (a FloodGuard regex on `text_en`/`text_bm`) was False for all 4 |
| Archive | **None observed.** `timestamp_start=2025-01-01 00:00:00@warning_issue__issued` returned the same 4 current records [probe]. Past warnings cannot be backfilled from this API |

### C. METMalaysia Web Service API: `api.met.gov.my` (**DEFERRED**, registration required)

| Field | Finding |
|---|---|
| Endpoint | `GET https://api.met.gov.my/v2.1/locations?locationcategoryid=STATE` → **401**, `WWW-Authenticate: METToken`, body `{"detail":"Authentication credentials were not provided."}` [probe]. `/v2/locations…` gave the same Python TLS failure; `/v1/`, `/v2/`, `/v2.1/`, `/docs/` → 404 [probe] |
| Registration | Landing page `https://api.met.gov.my/` (200) [probe]: "Get Your Access Token" form (`POST /register`, fields Full Name and Email Address), token delivered by email, then login (`POST /login`). **Stopped here: no registration was made and no token was used.** The developer guide is behind login [not verified] |
| Stated limits / scope | "up to 1,000 requests a day with a burstable limit of 3 requests per minute". Offers "the general weather forecast data"; v1 "deprecated". METMalaysia's Open Data page lists 7-day state/district/town forecasts, marine forecasts and latest radar/satellite images [probe] |
| Schema, issue time, archive | [not verified] (needs a token) |
| Disclaimer | Government "shall not be liable for any loss or damage" from use of API data [probe] |

Why DEFERRED: it needs a user-owned token, and the landing page offers "general weather forecast
data", which A already provides openly. Whether it adds an issue time or an archive is unknown. Revisit
only if A proves insufficient; the token must go in an environment variable, never in the repo.

### D. met.gov.my forecast and warning web pages (**NOT SUITABLE** as a v1 feed; reference only)

| Page | Finding [probe] |
|---|---|
| `/forecast/weather/{state,district,town,tourist}/<location_id>` | HTML, same 7-day text as A, no issue time. The location selector groups IDs by state; this was used to build `penang_locations.csv`. `https://…/district` 301-redirects to **`http://`** |
| `/data/ICN20032.html` | National daily forecast text ("Ramalan cuaca … pada 24 September 2026"), `Last-Modified` 2026-09-23 06:20 UTC. Gives a state-level morning/afternoon/night phrase for Pulau Pinang. The only issue-time proxy seen is HTTP `Last-Modified` |
| `/data/IWR30002.html` thunderstorm, `/data/IWR30007.html` continuous rain, `/data/IDM20016.html` wind/seas, `/data/IWR30003.html` cyclone | HTML bulletins: "Dikeluarkan pada pukul 9:00 pagi, 24 September 2026 … TIADA AMARAN" (thunderstorm). Continuous rain last issued 4 Sep 2026 09:00, "NO WARNING" (`Last-Modified` 2026-09-04). **Latest bulletin only; no archive URL** |
| RSS / CAP | No RSS, Atom or CAP link found on the home page or the pages above [probe]. Existence elsewhere is [not verified] |
| `robots.txt` | 404 |
| Terms | Copyright notice: website content may not be copied or redistributed for commercial purposes without written consent. Open Data page: "Semua set data terbuka … boleh dikongsi dan digunakan semula … untuk sebarang tujuan" |

### E. Radar and satellite (**NOT SUITABLE** for v1: rendered images only)

| Product | Finding [probe] |
|---|---|
| Peninsular radar | `/pencerapan/radar-semenanjung/` embeds `/data/radar_peninsular.gif`: `image/gif`, 162,015 B, `Last-Modified` 03:30:04 UTC, `ETag` present. One file overwritten in place; no numeric grid, no timestamped history URL |
| Peninsular satellite | `/pencerapan/semenanjung-malaysia/` embeds `/data/PEN_IR.png`: `image/png`, 418,271 B, `Last-Modified` 03:28:01 UTC. Same pattern |
| Numeric data | None found. The myclimate FDRS WMS portals linked from the home page were **not probed** [not verified]. No CV work is proposed |

### F. Surface observations: `/projection/rain/<WMO id>` (**DEFERRED**)

| Field | Finding [probe] |
|---|---|
| Penang stations listed | `48601` "L.T.A. Bayan Lepas", `48602` "TUDM Butterworth" (IDs from the page selector). 41 stations nationally |
| Format | HTML page with a Chart.js line chart. Data is an inline JS array of **24 values** with labels `"12PM" … "11AM"` (hour of day only, **no date**). Title "Carta Perubahan Hujan … Dalam Tempoh 24 Jam"; unit `mm` from the tooltip. Bayan Lepas: `0.2` at "1PM", others `0`. Butterworth: all `0` |
| Semantics | Interval (hourly total vs. running total), timestamp convention (hour start/end) and timezone are **not stated** [not verified]. Zero values are source data, never missing |
| Coordinates, QC, archive | None on the page. Historical observations appear to sit behind **myMETdata** (`mymetdata.met.gov.my`: login, fee schedule "Perintah Fi … 2010"), not probed further |

Why DEFERRED: scraping chart JS is brittle and gives only 2 Penang gauges with ambiguous timing,
while JPS already provides 56 Penang rainfall stations at 5-min resolution. Historical MET station
data is covered by the separate TASKS item "Verify data.gov.my historical weather coverage".

### G. Nowcasting: `/nowcasting/` (**NOT SUITABLE**)

HTML map (Leaflet) with inline markers: 14 Pulau Pinang points (IDs 10801–10814, lat/lon given).
Each point carries a categorical "Sekarang" (now) value and six 30-min-step forecasts (`Hujan`/`Tiada
Hujan`) plus "Tarikh kemaskini : 24/09/2026 11:20 AM" [probe]. The page's own disclaimer says the
information "should not be use to support operational observation, forecasting or disaster mitigation
operations" [probe]. Data quality: point `10801` "Ayer Itam" is placed at 6.2375, 100.2460, which is
outside Penang Island (Ayer Itam is about 5.40 N) [probe]. No archive.

## 2. Classification for FloodGuard v1

| Source | Live operational | Historical training | Class | Reason |
|---|---|---|---|---|
| A. data.gov.my forecast | Yes (daily 7-day text, 28 Penang IDs) | **No** (no archive, no issue time) | **RECOMMENDED** | Only official, open, structured, unauthenticated METMalaysia feed that covers Penang |
| B. data.gov.my warning | Context/display only | **No** (current only) | **OPTIONAL** | Has issue and valid times, but free-text geography, no Penang rain/thunderstorm warning observed, and `valid_from` anomalies |
| C. api.met.gov.my | Unknown | Unknown | **DEFERRED** | Needs a registered token. Content not verified |
| D. met.gov.my HTML pages | Reference/cross-check only | No | **NOT SUITABLE** | Duplicates A/B, scraping-only, latest bulletin only |
| E. Radar/satellite images | No | No | **NOT SUITABLE** | Rendered images, single overwritten file, no numeric data |
| F. `/projection/rain` | No | No | **DEFERRED** | Chart-embedded, 24 undated hourly values, 2 gauges; JPS is better |
| G. Nowcasting | No | No | **NOT SUITABLE** | The source disclaims operational/disaster use |

## 3. Temporal leakage

- **Forecast features cannot be backfilled.** The API serves only the current 7-day window, with no
  issue time and no date filter into the past (verified `[]`). Rebuilding "what the forecast said at
  time t" for historical training rows is impossible from this source. Filling it with later data or
  with observed weather would be **future-data leakage**.
- Forecast features must therefore be **collected forward-only from go-live**. Store each snapshot
  with FloodGuard `retrieved_at` as the only availability time, because the source gives no issue time.
  At training and serving time, use only snapshots with `retrieved_at <= prediction time`.
- `date` is a calendar day and the morning/afternoon/night hours are undocumented. Any mapping of a
  day-part onto the +30/+60/+120 min horizons is an assumption that must be documented before use.
- Warnings: the same forward-only rule applies. Use `issued`, not `valid_from` (which can precede
  `issued`), as the earliest availability time, and cap it at `retrieved_at`.
- Until forward-collected history exists (months of snapshots), v1 models trained on JPS history
  **cannot include METMalaysia forecast or warning features** without train/serve skew.

## 4. Smallest useful v1 integration (proposed, not implemented)

1. Poll `api.data.gov.my/weather/forecast` a few times per day (the exact issue hour is unknown, so
   hourly is safe at 24 requests/day, far below 4/min). Keep the 28 Penang IDs.
2. Store raw response bytes plus `retrieved_at`, and deduplicate on
   `location_id + date + content hash`. A change in content is a new forecast version: the first-seen
   `retrieved_at` becomes its availability time.
3. Optionally poll `/weather/warning` on the same schedule. Store it raw and display it. **No label mapping.**
4. Use this data for display and context in v1. Consider forecast features only after enough
   forward-collected history exists for a chronological validation.

The probe script `scripts/probe_metmalaysia.py` implements only the one-shot fetch, validation and
Penang filter. It has no loop.

## 5. Evidence files

| File | Content |
|---|---|
| `penang_locations.csv` | 28 Penang forecast location IDs; state evidence per row |
| `raw/forecast_PNG_trimmed_20260924T114040+0800.json` | Probe run 11:40:40 +08:00: **trimmed** to the 196 Penang rows (of 3,080), values verbatim, re-serialised |
| `raw/warning_20260924T114057+0800.json` | Probe run 11:40:57 +08:00: full body, byte-for-byte (4 records) |
| `raw/api_met_gov_my_v2.1_locations_401_20260924T1141+0800.txt` | `curl -D -` headers and body of the 401 (03:41:12 UTC) |
| `tests/fixtures/metmalaysia/` | Offline test fixtures from the 11:29:26 +08:00 capture (see its README) |

HTML pages, images and national payloads were inspected in a scratch directory and **not
committed** (sizes 0.1–0.9 MB).

## 6. Open questions / limitations

- Forecast issue hour and daily refresh time: [not verified]. Detecting it needs repeated
  snapshots across a day, which is out of scope here.
- Morning/afternoon/night hour boundaries: undocumented.
- Whether continuous-rain or thunderstorm warnings, when active, carry Penang-identifiable text in
  `/weather/warning`: not observed (none active during the probe).
- Meaning of `valid_from` < `issued` and of expired records still being returned.
- `api.met.gov.my` content, schema, archive and terms: blocked by registration.
- data.gov.my full Terms of Use text is unavailable (footer link `#`). CC BY 4.0 is stated only in the FAQ.
  Re-checked 2026-09-24 with attribution wording and the exact met.gov.my copyright text in
  `docs/DATA_LICENSING_AND_ACCESS.md`. The `api.met.gov.my` 401 capture in `raw/` is local-only (git-ignored).
- Python's CA bundle rejects `api.met.gov.my`'s chain, so a future client may need the OS trust store.
- The single-session sample (13 minutes) says nothing about long-term availability or schema stability.
