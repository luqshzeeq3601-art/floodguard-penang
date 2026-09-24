# GIS and Historical Flood Datasets (Pulau Pinang)

Verified 2026-09-24, 04:10–04:34 UTC (12:10–12:34 +08:00). Discovery only: no station master,
tables, labels, features, geometry pipeline or CRS transformation was built. Requests were
unauthenticated, sequential, at least 5 s apart, UA `FloodGuard-Penang-discovery/0.1 (research)`:
119 logged in `raw/probe_log_20260924.tsv` (112 GET, 7 HEAD; 105×200, 6×206 range, 2×404,
3×500, 3 TCP resets), 1 unlogged `curl` (maps2 reset, 04:13Z) and 15 by `scripts/probe_gis_sources.py`
(04:32:35Z `stations`: 1; 04:33:00–04:34:10Z `flood-history`: 14). No 429/403/CAPTCHA/login.
Largest transfer: the 1,320,015 B JPS station feed. The three 7.5–10 MB JPS GeoJSON layers were
only read as 4,096 B `Range` heads. No XLSX or PDF was downloaded. Python has no geopandas,
pyproj, shapely or pyarrow, so stdlib JSON was used.

Evidence labels: **[probe]** seen in a live response; **[doc]** official page/metadata text;
**[inferred]** reasoned from probe evidence; **[not verified]**.

## 1. Answer

- **Station coordinates: 56/56 rainfall and 22/22 water-level inventory rows (65 unique
  `jps_internal_id`) have officially published coordinates** in the JPS Public Infobanjir map
  feed `latestreadingstrendabc.json`, keyed by the same `stationid` (`a`), which matches verbatim
  (incl. the leading-space `" 5402002_"`) [probe]. Mapping: `penang_station_coordinates_jps.csv`.
- **River/basin/district:** JPS publishes Peninsular district, basin and main-river GeoJSON on the
  Penang JPS portal; DOSM publishes a small district GeoJSON (CRS84, 5 Penang districts) [probe].
- **Historical flood records exist for Penang** on the state GeoHub (`Sejarah_Banjir`, 27 layers,
  1991–2017, 2,222 features), with per-feature dates only for 2011–2015 and 2017 [probe].
  **Nothing event-dated overlaps the JPS 2024+ history.** Flood-prone/hotspot layers are
  undated, static inventories.
- **No official, structured, event-dated flood record usable to evaluate +30/+60/+120 min models
  was found.** Leading Phase 3 option: station-specific JPS water-level threshold exceedance
  (Section 5).

## 2. Candidates

Full attribute list per candidate: `penang_gis_candidate_layers.csv`.

| # | Dataset | Publisher / URL | Format · auth | CRS (evidence) | Temporal | Event-dated? | Penang | Class · role |
|---|---|---|---|---|---|---|---|---|
| A | Station map feed `latestreadingstrendabc.json` | JPS, `publicinfobanjir.water.gov.my/wp-content/themes/enlighten/data/` | JSON list, 2,725 records · none | Not declared; `/main/` calls `L.marker([loc.c, loc.d])`, so **WGS84 lat/lon inferred** | Current snapshot (Last-Modified 04:10:21Z, 04:30:22Z) | No | 129 records; all 65 inventory IDs | **RECOMMENDED** · station coordinates, basin/sub-basin |
| B | `BASIN_SEMENANJUNG.geojson` | JPS Pulau Pinang SPHTN portal, `infobanjirjps.penang.gov.my/SPHTN.Assets/maplayers/` | GeoJSON 10,194,589 B · none | No `crs` member → RFC 7946 default (lon/lat WGS84) | Last-Modified 2024-02-14 | No | Peninsular; Penang count not verified | **RECOMMENDED** · basin/catchment context (`RB_NAME`, `RB_ID`) |
| C | `SUNGAI_UTAMA_SEMENANJUNG.geojson` | same | GeoJSON 7,505,092 B · none | RFC 7946 default | 2024-02-14 | No | Has `STATE`/`STATE_CODE` | **OPTIONAL** · distance-to-river, dashboard |
| D | `SEMPADAN_DAERAH_SEMENANJUNG.geojson` | same | GeoJSON 8,186,440 B · none | RFC 7946 default | 2024-02-13 | No | Portal filters `KOD_NEGERI = '07'` | **OPTIONAL** · (E is smaller) |
| E | `administrative_2_district.geojson` | DOSM, `github.com/dosm-malaysia/data-open` | GeoJSON 947,755 B, 160 districts, simplified · none; DOSM Open Data Licence (reuse incl. commercial) | Explicit `urn:ogc:def:crs:OGC:1.3:CRS84` | Last commit 2022-06-22 | No | 5 districts, 74–140 vertices each | **RECOMMENDED** · district boundaries (dashboard/aggregation) |
| F | `Sejarah_Banjir` FeatureServer | Penang GeoHub `pegis.penang.gov.my/arcgis/rest/services/Hosted/` (ArcGIS Enterprise) | ArcGIS REST query · none (public) | Custom WKT `My_G_Cassini_Pulau_Pinang_&_Seberang_Perai` (GDM2000 Cassini, origin 5.420890092 N / 100.3446556 E), **no wkid** | 1991–2017 by layer; dated features 2011–2015, 2017 | Partly, date-level | 2,222 features | **OPTIONAL** · historical flood context/EDA; not evaluation labels |
| G | `Hotspot_Banjir`, `Kawasan_Banjir` | same | points + polygons · none | same WKT | Undated; items created 2024-04/06, `Kawasan_Banjir` modified 2026-07-13 | No | 124 hotspots | **OPTIONAL** · static hazard context, dashboard |
| H | `Lokasi_Berpotensi_Banjir` | same | points · none | same WKT | Snippet "Tahun 2023" | No | 93 | **OPTIONAL** · static hazard context |
| I | `Pusat_Pemindahan_Banjir` | same | points · none | same WKT | Modified 2026-07-15 | No | 377 | **DEFERRED** · dashboard only; holds contact-person fields |
| J | `Geobencana` | same | group of G/H layers | same WKT | Undated | No | 124/109/124 | **NOT SUITABLE** · duplicate of G/H |
| K | "Senarai Kawasan Banjir Pulau Pinang" (+ "Kawasan Hotspot Banjir … 2020") | Penang State via `archive.data.gov.my` (CKAN), CC BY | XLSX (2018 file 19,307 B; 2020 file HEAD → 500) · none | Tabular | 2018, 2020 lists | [not verified] | [not verified] | **DEFERRED** · file not downloaded; datastore API 404 |
| L | Flood-forecast MapServers (`floodforecasting_kln/phn/trn`), 2014 flood maps | JPS `maps.water.gov.my/arcgis/rest/services/floodforecast` | ArcGIS REST | wkid 3375 | — | No (modelled 100 m IFSAR maxima) | **None** (Kelantan/Pahang/Terengganu); `floodmap` folder 404 | **NOT SUITABLE** |
| M | `isohyetmap/*`, `rrai/rrai` | JPS `maps.water.gov.my` | Raster MapServer | wkid 4326 | Rolling 24 hourly rasters; `rrai` 185 hourly layers 2026-08-25 → 09-03 | — | National | **NOT SUITABLE** · rainfall rasters, no archive |
| N | `Fundamental/Sg_Semenanjung`, `TA_Road`, `TA_Railway` | JPS `maps2.water.gov.my` (used by `/main/`) | ArcGIS REST | [not verified] | — | — | — | **DEFERRED** · TCP reset on 3 HTTPS/HTTP attempts |
| O | MyDIMS "Laporan Bulanan" / "Laporan Situasi Semasa" | NADMA `mydims.nadma.gov.my/awam/…` | PDF (e.g. Julai 2026, 1,137,019 B) · none | — | Monthly Jan 2025 → Jul 2026; dated situation reports (e.g. 30-08-2026) | Likely date-level [not verified] | [not verified] | **DEFERRED** · only official source that may overlap 2024+; PDFs not read |
| P | InfoBencana JKM (`landing/index.php?a=7`) | JKM | HTML dashboard | — | Current only | No | 0 PPS open at probe time | **DEFERRED** · forward-only evidence |
| Q | MyGDI / MyGeoportal | PGN | Formal application letter (G2G/G2B/G2C/G2E) [doc] | — | — | — | — | **DEFERRED** · application required; stopped |
| R | Global fallbacks: Copernicus DEM / SRTM (elevation), HydroSHEDS (basins), Global Flood Database / Sentinel-1 (extents), geoBoundaries | third-party | — | — | — | — | — | **OPTIONAL** fallback only, not ground truth; not probed |

Not found / not probed: a PLANMalaysia, JUPEM DEM or MBPP/MBSP open flood layer; no official DEM
was located. The Penang JPS portal's `N9*.kmz` references are disabled template code
(`IsGmapEn = 'false'`) and were not fetched. `getdisse.php` (warning dissemination) returned `[]`.

### Detail: A. JPS station map feed

- Found in the `/main/` page JS: markers use `[loc.c, loc.d]`; popups link
  `rf-graph/?stationid=` + `a`. Keys are single letters and undocumented. Used: `a` station key,
  `b` name, `c` lat, `d` lon, `e` district, `f` state, `g` sub-basin, `h` main basin, `i` sensor
  types (`RF`, `WL`, `RF,WL`) [probe; meaning of c/d inferred from Leaflet usage and values].
- `a` unique nationally (2,725). District matches the inventory for 78/78 rows; basin/sub-basin
  match for 22/22 WL rows; the feed also gives basin for all 56 RF stations (new) [probe].
- Names differ for 18 of 56 RF rows and 1 of 22 WL rows: spacing/abbreviation, or a
  river-prefixed name (e.g. `27587` "Sg. Air Itam di Lorong Batu Lanchang (F2)" vs RF listing
  "Lorong Batu Lanchang (F2)"). Kept verbatim; IDs, not names, were joined.
- Precision: 4–6 decimals (6: 45, 5: 18, 4: 2 of 65). One shared point: `26186` and `27660`
  (both "Permatang Tok Jaya").
- The feed also carries live `n` (status) and `s` (trend) fields. `o` equals the listing "Normal"
  and `p` = level − `o` for all 22 WL rows [probe]. Out-of-inventory stations that stopped
  reporting in 2025 (e.g. `5503402_`, value `-9999`) still show `n = "Danger"`, so `n` is
  unreliable without value checks.
- Secondary cross-check (not used): the Penang JPS portal `WaterLevel/LatestData/All` lists 20 WL
  stations with its own IDs, display IDs and lat/lon at lower precision (e.g. 5.40219, 100.298 vs
  feed 5.402158, 100.29808 for display ID `1910131WL`).

### Detail: F. `Sejarah_Banjir` (historical floods)

Per-layer profile: `pegis_sejarah_banjir_layers.csv` (from the probe script).

| Years | Layers (point "Lokasi" / polygon "Kawasan") | Per-feature date |
|---|---|---|
| 1991, 1995, 1998, 2000, 2006, 2007, 2009 | 14 layers, 686 features | None (`tahun`, `tarikh_data` = data date only) |
| 1999 | 245 points, 80 polygons | Polygons: free-text `tarikh` on 28 (e.g. `25.10.1999`, `24.10.1999 - 26.101999`), 52 blank |
| 2011–2015 | 10 layers, 869 features | `tarikh` Date on every feature; 11–19 distinct dates per layer |
| 2017 | 342 points | `tarikh` Date: 2017-09-15 (65) and 2017-11-05 (277); free-text `masa` (e.g. `10:58 AM`, `2:23PM`, `11.45 AM`), `aras` (m, undocumented) |

- Date values are epoch ms at 00:00 UTC, i.e. calendar dates. Asia/Kuala_Lumpur day boundaries
  are **not** assumed. `masa` looks like a survey/observation time, not flood onset [inferred].
- Quality: layer 18 ("2012") holds one 2011-06-05 feature; layer 7 name typo "Banjr"; 2017
  `latitude`/`logitud` attributes partly null. The hotspot layers (G) store latitude in `lon` and
  longitude in `lot` (e.g. `lon` 5.408597, `lot` 100.313369). Nothing was corrected.
- Vector query works: `returnGeometry=true`, small WGS84 envelope (`inSR=4326`), 3 records returned
  in the native Cassini WKT (`raw/pegis_*_bbox_sample3_*.json`).
- Provenance caveat: all items are owned by portal account `ketuakelas`, with empty
  description, licence and access-information fields [probe]. The GeoBencana app text says the
  hotspot layer was generated from Penang state open hotspot data (i.e. K). Hosting is official
  (pegis.penang.gov.my, Penang state GeoHub); authorship/QC is [not verified].

## 3. Station-coordinate findings

- Coverage: **56/56 RF, 22/22 WL (65 unique IDs) from source A**, joined on verbatim
  `jps_internal_id` = feed `a`. No name matching, geocoding or inference was used.
- `penang_station_coordinates_jps.csv`: `latitude`/`longitude` are the source strings, plus
  source name/district/basin/sensor types, `coordinate_crs_note`, `source_last_modified`,
  `retrieved_at` (+08:00). It is **not** the station master (still TODO).
- Caveat: the feed is an undocumented, site-internal file; the CRS is inferred, not declared;
  coordinates are current values with no version history.

## 4. Flood-label feasibility

| Source | Event-dated | Resolution | Overlaps JPS 2024+ | Verdict |
|---|---|---|---|---|
| F `Sejarah_Banjir` | 2011–2015, 2017 (date); 1999 polygons (free text) | Calendar day; 2017 adds free-text times | **No** (latest 2017-11-05) | Context/EDA only |
| G/H hotspot, potential | No | — | — | Static context |
| K archive XLSX | [not verified] | — | 2018/2020 lists | Deferred |
| O NADMA MyDIMS PDFs | Likely, [not verified] | Day-level at best | Possibly (Jan 2025+) | Deferred; manual PDF extraction, needs user-approved download |
| JPS per-reading `severity` / threshold exceedance | Yes (5-min timestamps) | 5 min | Yes | **Leading Phase 3 option** |

Event dates were **not** derived from layer names or map appearance. A calendar-day flood record
cannot validate a +30/+60/+120 min horizon on its own; at most it can confirm that a day had
flooding somewhere near a station.

## 5. JPS threshold-label assessment (no labels created)

- Coverage: all four thresholds are published for **22/22** WL stations, ascending Waspada ≤
  Amaran ≤ Bahaya on all 22 (`data/metadata/jps/README.md`). Unit metres (graph-page JS).
- "Normal" is 0.00 on 14/22 rows. On the other 8 it equals feed `o`, and feed `p` = level − Normal
  [probe], so Normal behaves like a reference offset, not a flood stage [inferred]. **Do not use
  Normal as a label level.**
- Waspada (alert) / Amaran (warning) / Bahaya (danger) are usable station-level definitions.
  Caveats:
  - The history JSON returns current thresholds for 2024 windows, so they are not time-versioned
    (HISTORICAL_AVAILABILITY.md).
  - Per-reading codes `SL_NML`, `SL_ALT` and `ERROR` exist; the full code list is unknown.
  - **Cross-source disagreement:** the Penang JPS portal (SPHTN) was compared with the national
    listing for the 5 stations matched on display ID [probe, 04:15:59Z]. Alert/warning/danger
    differ for 3 of them:

| jps_internal_id (display ID) | National listing (A/W/D) | Penang portal (A/W/D) |
|---|---|---|
| 27587 (1910131WL) | 5.20 / 5.50 / 6.00 | 5.20 / 5.50 / 6.00 (Normal 0.00 vs 4.00) |
| 27612 (1910171WL) | 2.50 / 2.80 / 3.20 | 2.50 / 2.80 / 3.20 |
| LIMBUNGAN (5403444) | 1.30 / 1.50 / 1.80 | 1.30 / 1.45 / 1.75 |
| BUMBUNGLIMA (5504401) | 3.50 / 3.80 / 4.10 | 3.10 / 3.30 / 3.60 |
| 5302004_ (5403405) | 21.00 / 21.20 / 21.50 | 21.00 / 21.50 / 22.00 |

- Recommendation for Phase 3: define labels as exceedance of a named JPS level (e.g. Waspada or
  Amaran) in the 5-min water-level series within the horizon. Freeze the threshold source
  (national listing), value and capture date in the label version. Exclude `-9999`/`ERROR`
  readings. Measure event counts per station before committing. These labels mean "water-level
  threshold escalation", not observed flooding.

## 6. Static feature assessment (not added to the pipeline)

| Candidate feature | Source | Available at inference | Leakage risk | Verdict |
|---|---|---|---|---|
| Station lat/lon, district | A, E | Yes | None (static metadata) | Safe |
| Main basin / sub-basin | A (all 65), WL listing | Yes | None | Safe (categorical) |
| Distance to main river / basin membership | B, C (2024-02 files) | Yes | None (physical network) | Safe; needs GIS tooling not in `.venv` |
| Elevation | No official DEM found; global DEM fallback | Yes | None | Deferred |
| Flood-hotspot / potential-zone membership | G, H | Yes | **Possible.** Undated inventories compiled 2023–2026 (`Kawasan_Banjir` edited 2026-07-13) may reflect floods inside the 2024+ evaluation period | Only with a version frozen before the training period, or as context |
| Historical flood count near station | F (≤ 2017) | Yes | Low: all records predate JPS 2024+ history | Acceptable if computed only from pre-period records |
| Flood extents | F polygons | — | Mapped after each event; never a same-period feature | Not a feature |

## 7. Evidence files (`raw/`)

| File | Content |
|---|---|
| `probe_log_20260924.tsv` | UTC time, method (+Range), status, bytes, URL, key headers for 119 requests |
| `jps_latestreadingstrendabc_penang_trimmed_20260924T041054Z.json` | 129 Penang feed records, verbatim |
| `sphtn_*_bytes0-4095_20260924.geojson.part` | First 4,096 B of B/C/D (partial, not valid JSON) |
| `dosm_administrative_2_district_penang_trimmed_20260924.geojson` | E, 5 Penang features verbatim |
| `pegis_portal_search_banjir_trimmed_20260924.json` | GeoHub item metadata (owner, dates, extent) |
| `pegis_*_FeatureServer_20260924.json`, `pegis_Sejarah_Banjir_layer{0,25,26}_*.json` | Service/layer JSON (schemas, CRS WKT) |
| `pegis_Sejarah_Banjir_counts_*`, `…groupby_*`, `…sample5_*`, `…bbox_sample3_*` | Counts, date distributions, small attribute/geometry samples |
| `arcgis_services_root_*`, `arcgis_maps_floodforecasting_kln_MapServer_*` | JPS ArcGIS directory, Kelantan-only forecast service |
| `archive_datagovmy_datastore_*` | CKAN datastore 404 responses |

## 8. Reproduce

```text
.venv\Scripts\python.exe scripts\probe_gis_sources.py stations        # 1 request
.venv\Scripts\python.exe scripts\probe_gis_sources.py flood-history   # 14 requests
.venv\Scripts\python.exe -m pytest tests\test_probe_gis_sources.py     # offline
```

Exit codes: `0` ok, `2` schema change, `3` network failure.

## 9. Limitations

- Source A and the SPHTN/GeoHub services are undocumented or unlicensed for reuse. JPS pages say
  "Hakcipta Terpelihara"; the GeoHub items have empty licence fields. Terms review is the separate
  Phase 1 licensing task.
- Penang feature counts in B/C/D and the content of K and O were not checked, to avoid bulk or
  file downloads. `maps2.water.gov.my` was unreachable from this network.
- Only 5 stations could be compared for threshold consistency (display-ID match). The SPHTN
  portal uses its own station IDs.
- The semantics of `aras`, `masa`, `potensibanjir`, `thn_2kali` and `dalam_m` are undocumented.
