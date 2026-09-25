# Data Licensing, Terms and Access Constraints

Status: evidence review completed 2026-09-24 (07:03 UTC last request). Phase 1 task "Document
licensing/terms/access constraints".

**This is not legal advice.** It records what each publisher's own pages say, where they say it,
and what FloodGuard therefore does. Where a notice is silent or ambiguous the entry says UNKNOWN or
UNCERTAIN; silence is never read as permission. Whether any statutory exception (for example fair
dealing for research) applies is a legal question outside this document.

Evidence: 71 unauthenticated GETs, sequential, 3 s apart, UA
`FloodGuard-Penang-discovery/0.1 (research; licensing review)`, 06:45:01Z–07:03:07Z. Every legal or
access claim below cites a URL whose retrieval time, HTTP status and body sha256 are in
[`data/metadata/licensing/evidence/legal_pages_20260924.tsv`](../data/metadata/licensing/evidence/legal_pages_20260924.tsv).
Legal pages are copyrighted by their publishers, so only URL, hash and short quotes (< 15 words)
are stored. Page hashes are of dynamic HTML and will not reproduce byte-for-byte.

## 1. Kinds of notice (kept separate)

| Kind | Meaning here | Example |
|---|---|---|
| Website copyright notice | Covers a website "and its contents"; not written as a data licence | JPS, METMalaysia, MyGeoportal |
| Dataset licence | Attached to a named dataset in a catalogue | data.gov.my `air_pollution` (CC BY 4.0); archive.data.gov.my flood list (`cc-by`) |
| API / platform licence | Stated for data served by an API or platform | developer.data.gov.my FAQ (CC BY 4.0) |
| Repository licence | File in a code/data repository | DOSM `data-open` LICENSE.md; `datagovmy-meta` MIT |
| Portal-wide / item metadata | ArcGIS portal settings and item `licenseInfo` / `accessInformation` | Penang GeoHub (empty) |
| robots.txt | Crawler hint only. **Not permission** | JPS Public Infobanjir |

## 2. Classification vocabulary

- **OPEN**: a licence covering this source allows reuse including redistribution, without a requirement to credit the source when using the data (a condition to keep a licence notice with redistributed copies, as in MIT, may still apply).
- **PERMITTED WITH ATTRIBUTION**: an explicit licence covers this source and requires attribution.
- **INTERNAL/PROJECT USE ONLY**: permission limited to internal use (none assigned; no publisher grants this explicitly).
- **PERMISSION REQUIRED**: the publisher's notice requires prior written consent for the intended use.
- **UNKNOWN**: no licence or terms found for this source.
- **DEFERRED**: not used yet; terms not (fully) reviewable without registration, purchase, application or download.
- **NOT USED**: FloodGuard does not use it; terms recorded for completeness.

Per-use cells in Section 4 use: PERMITTED, PERMITTED WITH ATTRIBUTION, UNCERTAIN (terms do not
address it), PERMISSION REQUIRED, N/A (not planned).

## 3. Source matrix

Evidence date for every row: **2026-09-24** (UTC times in the evidence TSV).

### 3a. Identity, licence and action

| ID | Source | Publisher | Data used by FloodGuard | Access mechanism | Public / auth | Licence / copyright status (kind of notice) | Attribution requirement | Source URL | Classification | Required action |
|---|---|---|---|---|---|---|---|---|---|---|
| J1 | Public Infobanjir state listings | JPS (Jabatan Pengairan dan Saliran Malaysia) | Penang rainfall and water-level stations, latest values, thresholds | Undocumented site-internal HTML fragments (GET) | Public, no auth | JPS **website copyright notice**: content owned by JPS unless indicated; no part may be modified, copied, distributed, retransmitted, broadcast, displayed, reproduced, published, licensed, transferred, sold or commercially dealt with "without the express prior written consent of JPS" (water.gov.my/index.php/pages/view/342, EN; same text in BM in Public Infobanjir Terms, `/perkhidmatan/perkongsian-maklumat/`). Footer: "All Rights Reserved". No data licence, API terms or polling permission found | None published (no permission exists to attribute under) | https://publicinfobanjir.water.gov.my/ | **PERMISSION REQUIRED** | Written request to JPS (Section 8) before production polling, bulk history, public display or publication |
| J2 | Public Infobanjir date-range history JSON | JPS | 5-min rainfall / water level (≥ 2024), severity codes | Undocumented site-internal JSON (GET per station/window) | Public, no auth | Same JPS notice as J1 | None published | same | **PERMISSION REQUIRED** | Ask JPS whether bulk history must come via the Hydrology Division / HIS instead (JPS FAQ points data requests there) |
| J3 | Public Infobanjir map feed `latestreadingstrendabc.json` | JPS | Station lat/lon, basin, sub-basin | Undocumented static JSON (GET) | Public, no auth | Same JPS notice as J1 | None published | same | **PERMISSION REQUIRED** | Include coordinates/station metadata in the JPS request |
| J4 | `maps.water.gov.my` / `maps2` ArcGIS | JPS | None (flood-forecast services cover Kelantan/Pahang/Terengganu; maps2 unreachable) | ArcGIS REST | Public | Service `copyrightText` empty; JPS notice applies to JPS content | n/a | https://maps.water.gov.my/arcgis/rest/services?f=json | **NOT USED** | None |
| P1 | Penang JPS portal (SPHTN) GeoJSON: basin, main river, district | JPS Pulau Pinang | Candidate basin/river context; threshold cross-check | Static GeoJSON / JSON (GET) | Public, no auth | **No terms or copyright text found** on the portal home page; robots.txt 404. Whether the national JPS notice extends to this state portal is not stated | Unknown | https://infobanjirjps.penang.gov.my/ | **UNKNOWN** | Ask JPS Pulau Pinang together with J1–J3 |
| G1 | Penang GeoHub `Sejarah_Banjir`, `Hotspot_Banjir`, `Kawasan_Banjir`, `Lokasi_Berpotensi_Banjir` | Penang State (GeoHub, item owner account `ketuakelas`) | Historical flood points/polygons 1991–2017, hotspot/potential layers (EDA/context only) | ArcGIS REST FeatureServer (GET) | Public items, no auth | **Item** `licenseInfo` and `accessInformation` empty for all 5 feature-service items; services' `copyrightText` empty; the two items checked (`Sejarah_Banjir`, `Hotspot_Banjir`) belong to no anonymously visible group, so they are not published through the GeoHub open-data group (that group returns a 403 error body anonymously); **portal-wide** settings have no licence/terms key. Landing page describes the portal as geospatial information for government and public use (a description, not a licence) | Unknown | https://pegis.penang.gov.my/geoportal/sharing/rest/content/items/5ae1e704f8644bd4bedec12b2a6093b6?f=json | **UNKNOWN** | Ask Penang GeoHub / data owner (Section 8) |
| G2 | Penang GeoHub `Pusat_Pemindahan_Banjir` | Penang State | None (holds contact-person fields) | ArcGIS REST | Public | Same as G1; also contains personal data fields | Unknown | https://pegis.penang.gov.my/geoportal/sharing/rest/content/items/4077b9e22db64a1e970095ae367201ba?f=json | **DEFERRED** | Do not store or display personal fields; revisit only with permission |
| D1 | DOSM district boundaries `administrative_2_district.geojson` | DOSM | 5 Penang district polygons (dashboard/aggregation) | GitHub raw file | Public | **Repository/dataset licence** `LICENSE.md` "Open Data License": copy, publish, distribute, adapt and exploit commercially and non-commercially; no rights over personal data or third-party rights; must not suggest official status or DOSM endorsement; "as is" | **Not required** by the licence text. Credit recommended (Section 7) | https://github.com/dosm-malaysia/data-open/blob/main/LICENSE.md | **OPEN** | Keep the no-endorsement condition; credit DOSM |
| W1 | data.gov.my Weather API `/weather/forecast`, `/weather/warning` | METMalaysia data, served by data.gov.my (JDN) | Penang 7-day forecast text, warnings (live context; forward-only collection) | Documented REST API | Public, no auth | **API/platform licence**: developer.data.gov.my FAQ says data is open under CC BY 4.0; Weather API page says data is provided by MET Malaysia. The "Terms of Use" footer link is `#` (no page) | **Yes (CC BY 4.0 §3(a))**: credit creator/source, licence name + link, URI to source where practicable, indicate changes. **No attribution wording is prescribed** by data.gov.my; proposed wording in Section 7 | https://developer.data.gov.my/faq | **PERMITTED WITH ATTRIBUTION** | Add attribution wherever data or derived outputs are shown; ask data.gov.my for the Terms of Use text (link is `#`) |
| W2 | data.gov.my "Weather and Climate" dashboard | METMalaysia data on data.gov.my | Optional EDA climatology (Bayan Lepas, Butterworth, 2013–2022) | Next.js page payload (no API) | Public | **No licence on the dashboard page**; not a catalogue dataset. Whether the FAQ's CC BY 4.0 statement covers dashboard-only data is not stated | Unknown | https://data.gov.my/dashboard/weather-and-climate | **UNKNOWN** | Ask data.gov.my; until answered use for internal EDA only, publish nothing from it |
| W3 | data.gov.my catalogue `air_pollution` | DOE / DOSM via data.gov.my | None (NOT SUITABLE) | Catalogue API | Public | **Dataset licence** on catalogue page: CC BY 4.0 | CC BY 4.0 | https://data.gov.my/data-catalogue/air_pollution | **NOT USED** | None |
| W4 | archive.data.gov.my "Senarai Kawasan Banjir Pulau Pinang" (XLSX) | Kerajaan Negeri Pulau Pinang | None yet (file not downloaded) | CKAN catalogue (legacy) | Public | **Dataset licence** on CKAN page: `license_id` `cc-by`, title "Creative Commons Attribution", **no version**; portal footer "Hakcipta Terpelihara" | CC BY (version unspecified); no wording prescribed | https://archive.data.gov.my/data/en_US/dataset/senarai-kawasan-banjir-pulau-pinang | **DEFERRED** | If used: record version ambiguity, attribute Penang State Government + data.gov.my archive |
| W5 | `data-gov-my/datagovmy-meta` | data.gov.my (GitHub) | Dashboard metadata only (evidence) | GitHub | Public | **Repository licence** MIT (copyright + permission notice must accompany copies) | MIT notice if redistributed | https://github.com/data-gov-my/datagovmy-meta | **OPEN** | Raw copy kept local (no notice file needed) |
| M1 | met.gov.my web pages (forecast HTML, bulletins, radar/satellite images, nowcasting, `/projection/rain`) | METMalaysia | None (NOT SUITABLE / reference only) | Website | Public | **Website copyright notice** (`/info/kenyataan-hak-cipta`): content owned by the Government of Malaysia; no part may be modified, copied, distributed, published, licensed, transferred, sold "or dealt with for commercial purposes" without prior written consent. Whether "for commercial purposes" qualifies every verb is ambiguous; treated as covering all. Open-data page says MET open datasets may be shared and reused for any purpose, and lists the api.met.gov.my and data.gov.my channels | n/a | https://www.met.gov.my/info/kenyataan-hak-cipta | **NOT USED** | Do not scrape or republish website content |
| M2 | `api.met.gov.my` | METMalaysia | None (DEFERRED) | Token API (registration) | Registration | Open-data statement above; API landing: "free service", disclaimer, limits. API terms/developer guide behind login, **not reviewed** (no registration made) | Unknown | https://api.met.gov.my/ | **DEFERRED** | Review terms at registration (user action) |
| M3 | myMETdata | METMalaysia | None | Paid portal (login) | Account + fee (Fee Order 2010, amended) | Website copyright notice; purchase terms not reviewed | Unknown | https://mymetdata.met.gov.my/ | **DEFERRED** | Only if hourly MET station history is needed |
| Q1 | MyGDI / MyGeoportal | PGN (Pusat Geospatial Negara) | None | Formal application letter (G2G/G2B/G2C/G2E) | Application | MyGeoportal website copyright notice; release conditions set per application | Per release | https://www.mygeoportal.gov.my/ms/perkongsian-data-mygdi | **DEFERRED** | Apply only if a fundamental dataset is needed |
| N1 | NADMA MyDIMS reports / Portal Bencana | NADMA | None (PDFs not read) | Website/PDF | Public | No terms or copyright text found on MyDIMS pages; Portal Bencana shows a privacy policy only | Unknown | https://mydims.nadma.gov.my/awam/laporan-bulanan | **DEFERRED** | Ask before extracting event dates; PDFs not downloaded |
| N2 | JKM InfoBencana | JKM | None | Website | Public | "Terma & Syarat" link points to `#` | Unknown | https://infobencanajkmv2.jkm.gov.my/landing/ | **DEFERRED** | None now |
| S1 | Sentinel-1 SAR (optional module) | Copernicus / ESA | None | — | — | Not reviewed in this task | — | — | **DEFERRED** | Review when Phase 13 starts |
| S2 | Global fallbacks (Copernicus DEM, SRTM, HydroSHEDS, geoBoundaries) | various | None | — | — | Not reviewed | — | — | **NOT USED** | Review before any use |
| X1 | Google Maps JavaScript API (key embedded in JPS pages) | Google / JPS | None | — | — | FloodGuard never calls it; key belongs to JPS page code | — | — | **NOT USED** | See Section 10 (key audit) |

### 3b. Retrieval, storage and publication status

| ID | Automated retrieval | Local storage | Derived features / model training | Redistribution / public demo | Commercial / portfolio | Retention restrictions | Rate limits |
|---|---|---|---|---|---|---|---|
| J1–J3 | Technically possible; **no permission**. Discovery-scale only so far (≤ 2 req per poll, ≥ 2 s apart) | Discovery captures on disk, git-ignored | UNCERTAIN (not addressed by the notice) | PERMISSION REQUIRED | PERMISSION REQUIRED (notice bars commercial dealing and, read literally, any copying/display) | None stated | None published; observed none (Section 6) |
| J4 | Not used | Service JSON local only | N/A | N/A | N/A | None stated | None published |
| P1 | Technically possible; no terms | 4 KB range heads local only | UNCERTAIN | UNCERTAIN (treat as not permitted) | UNCERTAIN | None stated | None published |
| G1 | Technically possible; no terms | Service/sample JSON local only; minimised schema/statistics in test fixtures (flagged) | UNCERTAIN | UNCERTAIN (treat as not permitted) | UNCERTAIN | None stated | None published |
| G2 | Not planned | Service JSON local only | N/A | Not permitted (personal fields) | N/A | None stated | None published |
| D1 | Permitted | Trimmed Penang GeoJSON tracked | PERMITTED | PERMITTED (no endorsement implied) | PERMITTED | None stated | GitHub limits only |
| W1 | Permitted within 4 req/min | Trimmed captures tracked | PERMITTED WITH ATTRIBUTION | PERMITTED WITH ATTRIBUTION | PERMITTED WITH ATTRIBUTION | None stated | **4 requests/min** (429 beyond) |
| W2 | No API; page payload | Local only | UNCERTAIN (and NOT SUITABLE as features) | UNCERTAIN (treat as not permitted) | UNCERTAIN | None stated | Not published for pages |
| W3 | — | Tracked (2 tiny API bodies) | N/A | PERMITTED WITH ATTRIBUTION | PERMITTED WITH ATTRIBUTION | None stated | 4 requests/min |
| W4 | Not done | None | N/A | CC BY (version unspecified) | CC BY | None stated | — |
| W5 | — | Local only | N/A | MIT notice required | MIT | None | — |
| M1 | Not planned | None | N/A | PERMISSION REQUIRED | PERMISSION REQUIRED | None stated | robots.txt 404 (not permission) |
| M2 | Not done | None | Unknown | Unknown | Unknown | Unknown | 1,000 req/day, burst 3/min (landing page) |
| M3, Q1, N1, N2, S1, S2 | Not done | None | Unknown | Unknown | Unknown | Unknown | Unknown |

## 4. Per-source use assessment

Model training on copyrighted factual sensor data is marked UNCERTAIN wherever the terms do not
address it.

| Use | JPS J1–J3 | Penang SPHTN P1 | GeoHub G1 | DOSM D1 | Weather API W1 | Dashboard W2 |
|---|---|---|---|---|---|---|
| Live ingestion | PERMISSION REQUIRED (automated copying/storage; no API terms, no polling consent) | UNCERTAIN | N/A (static) | N/A (static) | PERMITTED WITH ATTRIBUTION (≤ 4 req/min) | N/A (frozen) |
| Historical training data acquisition | PERMISSION REQUIRED | N/A | N/A | N/A | N/A (no archive) | N/A (not suitable) |
| Internal analysis (EDA) | PERMISSION REQUIRED on a literal reading (copying); discovery captures already exist locally | UNCERTAIN | UNCERTAIN | PERMITTED | PERMITTED WITH ATTRIBUTION | UNCERTAIN |
| Derived features / model training | UNCERTAIN | UNCERTAIN | UNCERTAIN | PERMITTED | PERMITTED WITH ATTRIBUTION | UNCERTAIN |
| Map visualisation (internal) | PERMISSION REQUIRED (station coordinates are JPS content) | UNCERTAIN | UNCERTAIN | PERMITTED | PERMITTED WITH ATTRIBUTION | N/A |
| Public dashboard display | PERMISSION REQUIRED | UNCERTAIN (treat as not permitted) | UNCERTAIN (treat as not permitted) | PERMITTED (no endorsement) | PERMITTED WITH ATTRIBUTION | UNCERTAIN (treat as not permitted) |
| Screenshots / portfolio demo | PERMISSION REQUIRED (includes screenshots of JPS pages and of FloodGuard screens showing JPS values) | UNCERTAIN (treat as not permitted) | UNCERTAIN (treat as not permitted) | PERMITTED | PERMITTED WITH ATTRIBUTION | UNCERTAIN |
| Raw redistribution (repo, dataset release) | PERMISSION REQUIRED | UNCERTAIN (treat as not permitted) | UNCERTAIN (treat as not permitted) | PERMITTED | PERMITTED WITH ATTRIBUTION | UNCERTAIN (treat as not permitted) |
| Publication of processed / aggregated outputs (metrics, event counts, predictions) | UNCERTAIN (derived from JPS data; notice silent on derived facts) | UNCERTAIN | UNCERTAIN | PERMITTED | PERMITTED WITH ATTRIBUTION (indicate changes) | UNCERTAIN |

Consequence for the roadmap: Phase 2 (bulk JPS history) and Phase 10 (production JPS polling) have
**no documented permission**. Continuing them without a JPS answer is a risk the user must accept
explicitly; this document does not grant it.

## 5. Technical accessibility is not legal permission

- JPS endpoints need no login, CAPTCHA or key and return HTTP 200 to scripted requests;
  `robots.txt` disallows only `/wp-admin/`. None of this is permission: the copyright notice
  still requires prior written consent.
- The endpoints J1–J3 are undocumented site-internal XHR/JSON used by the JPS web pages. They are
  not offered as an API and carry no API terms or SLA.
- Penang GeoHub services are `access: public` ArcGIS items. Public sharing in ArcGIS controls
  visibility, not licensing; the licence fields are empty.
- data.gov.my is the only source whose API is documented **and** licensed (CC BY 4.0) **and**
  rate-limited in writing.
- A token API (api.met.gov.my) or a data portal (myMETdata, MyGDI) has terms FloodGuard has not
  seen; registration, purchase or application is a user decision.

## 6. Access etiquette (separate from licensing)

| Source | Documented limit | FloodGuard practice | Classification of etiquette |
|---|---|---|---|
| JPS Public Infobanjir | None published; no SLA; no polling permission | Discovery used sequential requests ≥ 2 s apart; proposed live design is **2 state-level requests per 5 min** (576/day), history only as targeted backfill. No 403/429/CAPTCHA observed in 47 live + 66 history requests | Conservative by design, **not** a permitted rate; keep discovery-only until JPS answers |
| data.gov.my API | **4 requests/min** per API; `429` when exceeded (developer.data.gov.my/rate-limit) | Hourly forecast/warning poll planned (≈ 48/day) | Within documented limit |
| api.met.gov.my | 1,000 requests/day, burst 3/min (landing page) | Not used | — |
| Penang GeoHub | None published | ≥ 5 s between requests; counts/statistics and ≤ 5-record samples only | Conservative |
| GitHub (DOSM) | GitHub API limits | One-off downloads | — |

Always: identify with a descriptive User-Agent, no parallel requests, bounded retries with backoff,
stop on 403/429 or CAPTCHA, never bypass access controls.

## 7. Disclaimer and attribution

### JPS disclaimer and the "not official" rule

- JPS disclaims liability for loss or damage from use of information on its websites
  (water.gov.my `/pages/view/338`; Public Infobanjir `/penafian/`).
- The Public Infobanjir disclaimer states the site was developed for flood forecasting and warning
  **for the Kelantan, Terengganu and Pahang river basins only**. Penang is not among them.
- METMalaysia and api.met.gov.my carry equivalent no-liability disclaimers. The DOSM licence
  forbids suggesting official status or endorsement.

Therefore FloodGuard must **never** be presented as an official JPS, METMalaysia, NADMA or Penang
State warning service, and its outputs must never be worded as official warnings.

Proposed disclaimer (for README and a future UI footer/about page; frontend and `design.md` not
edited here):

> FloodGuard Penang is an independent, non-official research and portfolio project. It is not
> affiliated with, endorsed by, or a service of JPS (Department of Irrigation and Drainage
> Malaysia), MET Malaysia, NADMA or the Penang State Government. Its risk estimates are
> experimental model outputs, not official flood forecasts or warnings. For official information
> follow JPS, MET Malaysia and your local authorities. Do not use FloodGuard for safety decisions.

### Attribution (only where a licence requires or allows it)

| Source | Required? | Proposed text (publisher prescribes no wording unless stated) |
|---|---|---|
| W1 Weather API | **Yes**, CC BY 4.0 §3(a) | "Weather forecast and warning data: MET Malaysia, via the data.gov.my Weather API (https://api.data.gov.my/weather), licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Filtered to Pulau Pinang and reformatted by FloodGuard." |
| W3 / W4 if ever used | Yes, CC BY | "<dataset title>, <publisher>, via data.gov.my, CC BY 4.0 [W4: CC BY, version not stated]. Modified by FloodGuard." |
| D1 DOSM boundaries | Not required; recommended | "District boundaries: Department of Statistics Malaysia (DOSM), dosm-malaysia/data-open, DOSM Open Data Licence." |
| W5 datagovmy-meta | MIT notice only if the file is redistributed | Include the MIT licence text with the copy |
| J1–J3, P1, G1 | **No permission exists to attribute under.** Attribution does not replace consent | Wording to be taken from JPS / GeoHub replies |

Where attribution must appear (proposed structure, to be built when the consumer exists):

- `DATA_SOURCES.md` (future, repo root): one entry per source with publisher, URL, licence and
  version, classification, retrieval method, attribution text, modification note, evidence date.
- `README.md`: "Data sources and disclaimer" section linking to this document (added).
- Dataset cards (Phase 7): licence and attribution per dataset version.
- Frontend / Streamlit: persistent footer "Data: MET Malaysia via data.gov.my (CC BY 4.0) · DOSM ·
  … · Not an official warning service", plus an About/Sources page mirroring `DATA_SOURCES.md`.
  JPS/GeoHub items appear only after permission, with the wording they require.

## 8. Permission and clarification requests (drafted, not sent)

Nothing was sent. The user decides whether and how to contact publishers.

| Publisher | What to ask | Official channel (as published) |
|---|---|---|
| JPS (national) | (1) Consent for automated retrieval of the Penang state listings every 5 min (2 requests) and targeted history backfill; preferred rate. (2) Whether bulk 5-min history should be requested from the Water Resources & Hydrology Division / HIS instead. (3) Consent to store raw copies, derive features and train models. (4) Consent to show readings, thresholds and station locations in a non-official public demo, and to publish aggregated results. (5) Consent to keep small excerpts as test fixtures in a public repository. (6) Required attribution wording. | Contact form: https://www.water.gov.my/index.php/pages/view/1556 ; Public Infobanjir feedback: https://publicinfobanjir.water.gov.my/perkhidmatan/maklum-balas/ ; data requests per FAQ: Hydrology Division, JPS Jalan Ampang (FAQ https://www.water.gov.my/index.php/pages/view/871) |
| JPS Pulau Pinang | Same as JPS for Penang stations, plus the SPHTN GeoJSON (P1) and which threshold set is authoritative | Pulau Pinang hydrology office listed at https://publicinfobanjir.water.gov.my/mengenai-kami/hubungi-kami/ (office e-mail `pnp.jpspp@water.gov.my`) |
| Penang GeoHub / state data owner | Licence for `Sejarah_Banjir`, `Hotspot_Banjir`, `Kawasan_Banjir`, `Lokasi_Berpotensi_Banjir` (internal analysis, derived features, public maps, redistribution); data owner and QC; attribution wording | Portal "Contact Us" link (portal settings): https://idirektori.penang.gov.my/carian_pegawai |
| data.gov.my (JDN) | (1) Text of the Terms of Use (footer link is `#`). (2) Whether CC BY 4.0 covers dashboard-only data (W2). (3) Preferred attribution wording for the Weather API | `help.dtsa@jdn.gov.my` (developer FAQ) |
| METMalaysia | Only if M1–M3 are ever used: reuse terms for website products and myMETdata purchases | General `mmd@met.gov.my`; data purchase `klim@met.gov.my` (https://www.met.gov.my/hubungi-kami/alamat-pejabat) |
| PGN (MyGDI) | Only if a fundamental dataset is needed: formal application with sample letter | https://www.mygeoportal.gov.my/ms/perkongsian-data-mygdi |

## 9. Repository policy for third-party evidence

1. **Raw captures whose rights are not granted or unknown stay local.** `data/metadata/*/raw/*` is
   git-ignored except our own `probe_log_*.tsv` and captures under a verified open licence (DOSM
   GeoJSON excerpt, data.gov.my API bodies incl. the Weather API, catalogue index).
2. **Reproducibility is kept by manifest.** Every file under `data/metadata/*/raw/` (tracked or
   not) is listed in [`data/metadata/RAW_EVIDENCE_MANIFEST.csv`](../data/metadata/RAW_EVIDENCE_MANIFEST.csv)
   with source URL, retrieval time (UTC), size, sha256, git blob id in commit `51c4b6e`, rights
   basis and repo status. The probe scripts regenerate captures.
3. **Commit only**: our code, our documents, derived metadata (URLs, timestamps, hashes, schema
   notes, counts), small parser fixtures, and data under a verified open licence with attribution.
4. **Test fixtures (decision).** JPS fixtures (`tests/fixtures/jps/`, ≤ 9.5 KB each) and the
   JPS/GeoHub fixtures in `tests/fixtures/gis/` are retained, **flagged PERMISSION REQUIRED /
   UNKNOWN**, because the offline parser tests (89 in the JPS and GIS test modules) assert on their exact source values and synthetic
   rewrites would change what the tests prove. They were minimised where the tests allow: the JPS
   map-feed fixture now keeps only the 9 parser keys for 67 records (was 40 keys × 131 records,
   76 KB → 13 KB; live readings, status and trend removed); the GeoHub layer fixture keeps only
   id/name/type/geometry type/field name+type (41 KB → 2.8 KB). If JPS or GeoHub declines, or
   before any public demo, replace them with clearly labelled synthetic fixtures.
5. **Derived station inventories** (`data/metadata/jps/*.csv`, `data/metadata/gis/penang_station_coordinates_jps.csv`)
   remain tracked because the offline tests read them. They contain JPS station metadata
   (names, IDs, thresholds, coordinates, one snapshot of levels): **flagged PERMISSION REQUIRED**,
   same decision rule as item 4.
6. **No screenshots** of JPS, GeoHub or MET pages, or of FloodGuard screens showing their data, are
   published until permission is recorded here.
7. **Secrets and third-party keys**: never committed; embedded third-party keys are redacted in
   fixtures (Section 10).

### Untracked on 2026-09-24 (`git rm --cached`, files kept on disk)

| Directory | Untracked | Kept tracked |
|---|---|---|
| `data/metadata/jps/raw/` | 8 (4 listing HTML, 4 history JSON) | 0 |
| `data/metadata/gis/raw/` | 24 (1 JPS feed, 2 JPS ArcGIS, 3 SPHTN heads, 16 GeoHub, 2 CKAN 404) | 2 (probe log, DOSM excerpt) |
| `data/metadata/data_gov_my/raw/` | 4 (2 dashboard payloads, dashboard station list, datagovmy-meta JSON) | 5 (probe log, catalogue index, 3 API bodies) |
| `data/metadata/metmalaysia/raw/` | 1 (api.met.gov.my 401 capture) | 2 (Weather API forecast, warning) |
| **Total** | **37** | **9** |

Exact per-file status: `repo_status` column of the manifest.

**Already public.** Commit `51c4b6e` is pushed to a public GitHub repository, so every untracked
file, and the Google Maps key below, **remains in public history**. Untracking only stops future
commits from carrying them. Removing them from history (rewrite + force-push) or making the
repository private is the **user's decision**; nothing was rewritten or pushed.

## 10. Google Maps key audit (2026-09-24)

Pattern `AIza[0-9A-Za-z_-]{20,}` over all raw evidence and fixtures (tracked and untracked) and
`git grep` over the tracked tree:

| Path | Status before | Action |
|---|---|---|
| `tests/fixtures/jps/searchresultrainfall_PNG_trimmed.html` | tracked, 1 occurrence (JPS page `<script src>` boilerplate) | Replaced with `REDACTED_GOOGLE_MAPS_KEY`; no test reads it; recorded in `tests/fixtures/jps/README.md` |
| `data/metadata/jps/raw/searchresultrainfall_PNG_20260924T015744+0800.html` | tracked | Untracked + git-ignored (kept locally, unmodified) |
| `data/metadata/jps/raw/searchresultrainfall_PNG_20260924T075653+0800.html` | tracked | Untracked + git-ignored (kept locally, unmodified) |

After the change `git grep` finds no key in the tracked tree. The key is served by JPS to every
visitor and is not a FloodGuard secret; FloodGuard never used it. It still exists in public
history (commit `51c4b6e`, all three paths).

## 11. Limitations

- One day of evidence; notices can change. Re-check before any publication or permission request.
- Pages were read as delivered to an anonymous client; no registration, purchase, application or
  PDF/XLSX download was made, so M2, M3, Q1, N1 and W4 terms are incomplete.
- Some notices are bilingual; the EN and BM JPS copyright texts match in substance, but only the
  publisher can say which governs.
- The JPS notice is a website notice; whether JPS treats telemetry values as "contents" in the same
  way, and whether statutory exceptions apply, is for JPS or a lawyer, not this document.
- Sentinel-1 and the global fallback datasets were not reviewed.
