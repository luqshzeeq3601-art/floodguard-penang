# Station Master Design

Status: Phase 1 task "Define station master table", 2026-09-24. Design plus a local, offline build.
No database table, migration, ingestion, feature or label was created.

- Code: `src/floodguard/station_master.py` (pure logic), `scripts/build_station_master.py`
  (one-shot local build, no network).
- Tests: `tests/test_station_master.py`. Fixtures: `tests/fixtures/station_master/` (all synthetic).
- Real output: `data/local/station_master/{sites,sensors,thresholds}.csv`. **Git-ignored, local
  only** (see Licensing below).

## 1. Identity model

```text
SITE (fg_site_id)  1 ────< 1..n  SENSOR (fg_sensor_id)  1 ────< 0..n  THRESHOLD (fg_threshold_id)
   monitoring location             one measurement type               WATER_LEVEL sensors only;
   coordinates, district, basin    at one site (≤ 1 per type)         one row per type × source
                                                                      × capture (versioned)

OBSERVATION identity = (source, fg_sensor_id, observation_time)          (section 12)
upstream pre-canonical dedup key = (jps_internal_id, measurement_type, observation_time)
```

- A **site** is a monitoring location. A **sensor** is one measurement type at a site:
  `RAINFALL` or `WATER_LEVEL`. A site has 1..n sensors and at most one sensor per type.
- Every sensor belongs to exactly one site. A site with no sensor is never emitted.
- `jps_internal_id` (graph-link `stationid`) and `jps_display_station_id` ("ID Stesen") are
  **source identifiers only**. They are stored verbatim and are never FloodGuard primary keys.
- FloodGuard-derived fields are prefixed `fg_`. Unprefixed fields are copied verbatim from a
  named source, or are constants (`source`, `unit`, `measurement_type`).
- There is no freshness, latest-observation or generic status column. Those are observation-time
  properties (`fg_live_status` in `data/metadata/jps/LIVE_ACCESS.md`), not station identity.

## 2. Source identifier rules

| Identifier | Scope | Rule |
|---|---|---|
| `jps_internal_id` | Monitoring site | Stored byte-for-byte (one real value has a leading space). Unique within each listing in every run observed. Both listings use the same value for a site with both sensors (13 real cases). |
| `fg_source_site_key` | Key derivation only | `jps_internal_id` with outer whitespace stripped. Case is kept, because JPS IDs such as `LIMBUNGAN` may be case-sensitive. Rejected if empty or if it contains inner whitespace. Any raw value that differs from the key sets `WHITESPACE_NORMALISED_SOURCE_ID`. |
| `jps_display_station_id` | Sensor | Stored verbatim. It is not unique, and it can be blank or read "No Data", so it is never a join key. Blank and "No Data" set `MISSING_DISPLAY_ID`. The same value on more than one row of one listing sets `DUPLICATE_DISPLAY_ID`. |

## 3. Key generation

**Choice: UUIDv5 under a pinned FloodGuard namespace.**

```text
FG_NAMESPACE     = uuid5(NAMESPACE_URL, "urn:floodguard-penang:station-master")
                 = ea5bad5b-553a-52a4-b428-73d204244a21          (pinned literal in code + test)
fg_site_id       = uuid5(FG_NAMESPACE, "site/v1|<source>|<fg_source_site_key>")
review site      = uuid5(FG_NAMESPACE, "site/v1|<source>|<fg_source_site_key>|review|<sensor_type>")
fg_sensor_id     = uuid5(FG_NAMESPACE, "sensor/v1|<source>|<fg_source_site_key>|<sensor_type>")
fg_threshold_id  = uuid5(FG_NAMESPACE, "threshold/v1|<fg_sensor_id>|<threshold_source>|<type>|<captured_at ISO>")
source           = JPS_PUBLIC_INFOBANJIR
```

The inputs are the source name, the normalised source key and the type, and nothing else. Names,
readings, districts, coordinates and discovery timestamps do not change an ID. Threshold IDs
include `captured_at` because each capture is a new version.

| Option | Stability | Collision risk | Verdict |
|---|---|---|---|
| Raw `jps_internal_id` as PK | Breaks on whitespace variants and cannot tell sources apart | Display IDs already collide | Rejected: the brief forbids source IDs as PKs |
| Readable composite (`JPS:27587:WL`) | Stable | None within a source | Rejected: it exposes the source key format, has no fixed width, and is awkward for a second source |
| Short hash (for example the first 12 hex digits of SHA-256) | Stable | About 48 bits. Negligible for 78 rows, but the truncation length becomes an extra decision | Viable |
| **UUIDv5, pinned namespace** | Stable, standard (RFC 9562) and fixed width. Maps to PostgreSQL `uuid` (ADR-0003) | 122-bit SHA-1-derived. Collision detection is still run | **Chosen** |

Why `fg_sensor_id` is derived from `(source, key, sensor_type)` and not from `fg_site_id`: a
sensor keeps its ID if a review moves it between a review site and the canonical site. It also
matches the upstream observation key `(jps_internal_id, measurement_type)`.

Risks and how they are handled:

| Risk | Handling |
|---|---|
| Whitespace variants (`" 5402002_"` vs `"5402002_"`) | Both give the same key and ID. The raw value is kept and the site is flagged. |
| Two raw IDs in **one** listing that normalise to the same key, or an exact duplicate | The build stops (`StationMasterError`). Sensor identity is undefined, so a person must decide. |
| Two map-feed records with the same key | Coordinates are withheld and the site is flagged `SOURCE_ID_COLLISION`. A shared ID is then not merged. |
| UUID collision between two different key inputs | Grouping makes the key inputs unique before hashing, so a duplicate generated ID can only be a hash collision. `validate_station_master` fails on any duplicate `fg_site_id`, `fg_sensor_id` or `fg_threshold_id`. A test forces a collision to prove this. |
| Station renamed | The ID is unchanged. The name is an attribute (tested). |
| Sensor type added later (for example WL at a site that was RF-only) | The existing site and sensor IDs are unchanged, and a new sensor is added (tested). |
| JPS reuses an internal ID for a different physical site | The ID alone cannot detect this. A future rebuild must compare the district, basin and coordinates with the previous local master. A change must go to manual review before it is accepted. That comparison is not implemented, because only one capture exists. |
| JPS renames an internal ID | The renamed ID produces a new site and new sensors. Linking the old and new IDs is a manual mapping decision. |
| Recipe change | The `v1` tags and the pinned literal IDs in `test_namespace_and_id_algorithm_are_pinned` make any change deliberate. |

## 4. Merge criteria (shared `jps_internal_id`)

The rainfall and water-level rows with the same key become **one site** only if **every** check
against the single official map-feed record for that key passes:

1. The same `fg_source_site_key`, after whitespace normalisation only. Rows are **never** merged by
   name, and never by display ID.
2. Exactly one map-feed record (`penang_station_coordinates_jps.csv`) exists for the key. Every
   sensor then resolves to that same `latitude`/`longitude` pair, so the coordinates match
   **exactly** (tolerance 0, compared as the verbatim source strings).
3. The listing `district` equals the feed district exactly. `state` is compared
   case-insensitively (the listings print "Pulau Pinang" and the feed prints "PULAU PINANG").
4. Where the listing has a basin (water level only), `main_basin` and `sub_basin` equal the feed
   values exactly.

**Ambiguity policy.** A sensor that fails any check is **not merged**:

- The canonical site `fg_site_id = site(key)` is anchored to the official feed record and keeps
  the sensors that match it.
- Each non-matching sensor gets its own review site (`review|<sensor_type>` key) with no
  coordinates. Both the canonical site and the review site are flagged `AMBIGUOUS_SITE_MAPPING`.
- If a shared ID has no single feed record, both sensors go to review sites.
- An unshared ID with no feed record is kept as a normal site flagged `MISSING_COORDINATES`.
- Different IDs at identical coordinates are never merged. They are flagged
  `COLOCATED_WITH_OTHER_SITE`.

When a person resolves a review, the review site ID is retired. The sensor ID does not change.

## 5. Schemas

### Site (`sites.csv`)

| Field | Source / rule |
|---|---|
| `fg_site_id` | UUIDv5 (section 3) |
| `fg_source_site_key` | Normalised `jps_internal_id` (key derivation only) |
| `source` | `JPS_PUBLIC_INFOBANJIR` |
| `jps_internal_id` | Raw value from the map feed, or from the listing when there is no feed record |
| `fg_site_name` | Derived display name: the feed name, else the WL listing name, else the RF listing name, with runs of whitespace collapsed. Not an identifier. |
| `jps_map_feed_name` | Feed name, verbatim (the sensor listing names are on the sensor rows) |
| `state`, `district` | Listing values (checked against the feed) |
| `latitude`, `longitude` | Feed strings, verbatim (4–6 decimals). Blank when missing, collided or under review. |
| `coordinate_source` | Feed URL (`latestreadingstrendabc.json`) |
| `fg_crs_assumption` | `EPSG:4326 (inferred)`. The feed declares no CRS; WGS84 is inferred from Leaflet `L.marker([lat, lon])`. |
| `main_basin`, `sub_basin` | Feed values; the WL listing is the fallback |
| `fg_first_seen_at`, `fg_last_verified_at` | Earliest and latest capture time among the evidence for the site (+08:00). This is when FloodGuard first saw the metadata, not when the station was commissioned. |
| `fg_quality_flags` | Pipe-separated, sorted (section 7) |
| `fg_schema_version` | `station_master/v1` |

### Sensor (`sensors.csv`)

| Field | Source / rule |
|---|---|
| `fg_sensor_id`, `fg_site_id` | Section 3 |
| `sensor_type` | `RAINFALL` / `WATER_LEVEL` |
| `source` | `JPS_PUBLIC_INFOBANJIR` |
| `jps_internal_id`, `jps_display_station_id`, `jps_sensor_name` | Listing row, verbatim |
| `measurement_type`, `unit` | `rainfall`/`mm`, `water_level`/`m` (units from official labels; see `HISTORICAL_AVAILABILITY.md`) |
| `fg_expected_listing_interval_minutes` | `15` when the listing name contains "(F2)" (LIVE_ACCESS.md: the F2 network advanced together in 15-min steps over a 23-min sample). Blank otherwise, because non-F2 stations publish asynchronously with no verified cadence. History rows are 5-min, which is a different property. |
| `source_url` | Listing endpoint |
| `fg_first_seen_at`, `fg_last_verified_at` | Listing capture time (`discovered_at`) |
| `fg_quality_flags`, `fg_schema_version` | As for site |

### Threshold (`thresholds.csv`, WATER_LEVEL sensors only)

| Field | Source / rule |
|---|---|
| `fg_threshold_id` | Section 3 (versioned by `captured_at`) |
| `fg_sensor_id` | Must reference a `WATER_LEVEL` sensor. The builder and the validator both reject any other type. |
| `threshold_type` | JPS terms kept in Malay: `NORMAL`, `WASPADA` (alert), `AMARAN` (warning), `BAHAYA` (danger) |
| `value`, `value_raw` | Decimal and published text (for example `0.00`) |
| `unit` | `m` (graph-page tooltip "Waspada: …m"; the listing header has no unit) |
| `threshold_source` | `JPS_NATIONAL_LISTING` (Public Infobanjir state listing) or `JPS_PENANG_PORTAL` (SPHTN `WaterLevel/LatestData/All`) |
| `source_url`, `captured_at`, `source_verified_at` | Capture of that source (+08:00) |
| `valid_from` | Blank: JPS publishes no validity period |
| `provenance` | File and column (national), or the doc table (Penang) |
| `fg_label_eligible` | `false` for `NORMAL`, `true` otherwise |
| `fg_quality_flags` | `THRESHOLD_PROVENANCE_CONFLICT` when sources disagree for the same sensor and type |

**Threshold versioning and limitations**

- Each (sensor, type, source, capture) is one immutable row. A later capture adds rows and never
  overwrites earlier ones. Label versions must pin `fg_threshold_id` values.
- JPS history downloads return **current** thresholds even for 2024 windows
  (`HISTORICAL_AVAILABILITY.md`). The values are therefore "as seen at `captured_at`" and cannot
  be treated as valid over any past period. `valid_from` stays blank.
- `NORMAL` is stored as source metadata but is **never label-eligible**. It is `0.00` on 14 of 22
  stations. On the other 8 it equals the map-feed offset `o`, with feed `p` = level − Normal, so it
  behaves like a reference offset, not a flood stage (`GIS_FLOOD_DATASETS.md` section 5).
- Penang-portal values come from the comparison table in `GIS_FLOOD_DATASETS.md` section 5. That
  table has the 5 stations matched on display ID and was captured in one probe, logged at
  2026-09-24T04:15:59Z. Only Waspada/Amaran/Bahaya are parsed. The build fails if the table's
  national columns disagree with the national listing. Nothing was re-fetched.
- Neither source is preferred at this stage. Choosing a threshold source for labels is a Phase 3
  decision; `GIS_FLOOD_DATASETS.md` recommends freezing the national listing.
- Rainfall sensors never get thresholds. The rainfall history JSON carries
  `info.light/moderate/heavy/veryheavy`, but those are intensity classes with an unlabelled
  unit and period, not flood thresholds.

## 6. Provenance rules

- Every value on a record comes from one named source row. The URL and capture time are on the
  record, and nothing is inferred from names.
- Raw source strings are never repaired. Derived forms are separate `fg_` fields.
- Timestamps are timezone-aware ISO-8601 in +08:00 (Asia/Kuala_Lumpur). The validator rejects
  naive times.
- Inputs: `data/metadata/jps/penang_rainfall_stations.csv` and `penang_water_level_stations.csv`
  (listing captures 2026-09-24T01:57:44 and 02:01:23 +08:00),
  `data/metadata/gis/penang_station_coordinates_jps.csv` (feed retrieved 12:32:35 +08:00) and
  `data/metadata/gis/GIS_FLOOD_DATASETS.md` section 5.

## 7. Quality flags

| Flag | Level | Meaning |
|---|---|---|
| `MISSING_DISPLAY_ID` | sensor | Display ID is blank or "No Data" |
| `DUPLICATE_DISPLAY_ID` | sensor | The same display ID appears on more than one row of the same listing |
| `AMBIGUOUS_SITE_MAPPING` | site | A shared ID failed a merge check (section 4); manual review needed |
| `CRS_INFERRED` | site | Uncertain coordinates: the CRS is not declared by the source |
| `MISSING_COORDINATES` | site | No usable official coordinates (none, collided, or under review) |
| `SOURCE_ID_COLLISION` | site | More than one coordinate record normalises to the same key |
| `WHITESPACE_NORMALISED_SOURCE_ID` | site | A raw `jps_internal_id` differs from its key |
| `MISSING_BASIN` | site | Main basin or sub-basin is blank |
| `SENSOR_TYPES_SOURCE_MISMATCH` | site | The feed's sensor types (`RF`, `WL`, `RF,WL`) differ from the listings containing the ID. No sensor is created from the feed alone. |
| `COLOCATED_WITH_OTHER_SITE` | site | Another key has identical official coordinates (not merged) |
| `THRESHOLD_PROVENANCE_CONFLICT` | threshold | National and Penang-portal values differ for this sensor and type |

## 8. Synthetic examples

The golden output from the synthetic fixtures is in `tests/fixtures/station_master/expected/`. The
fixture README lists the case behind each synthetic key. Excerpt (columns trimmed):

```text
sites.csv
fg_site_id                            key     fg_site_name          district                 lat       lon        flags
e92e57cd-306b-5067-a757-b78cee051191  SYN001  Synthetic Alpha (F2)  Timur Laut Pulau Pinang  5.400001  100.300001 CRS_INFERRED
d46269e6-9871-5ac9-a4a3-214c213ee445  SYN007  Synthetic Golf (F2)   Seberang Perai Tengah    5.360000  100.430000 AMBIGUOUS_SITE_MAPPING|CRS_INFERRED
6aeb699a-60b7-50f4-9010-94248b7c7d86  SYN007  Synthetic Golf WL     Seberang Perai Selatan   -         -          AMBIGUOUS_SITE_MAPPING|MISSING_COORDINATES

sensors.csv
fg_sensor_id                          fg_site_id   type         jps_internal_id  display    interval
3f881755-e14a-5811-9f45-93b5dbf5ab31  e92e57cd…    RAINFALL     SYN001           9990011RF  15
4c2f443b-168a-54a1-88f8-83b2930ebff3  e92e57cd…    WATER_LEVEL  SYN001           9990011WL  15
262a2ed2-7935-5543-a50e-6729d8b80c3e  6aeb699a…    WATER_LEVEL  SYN007           9990071WL  -

thresholds.csv (sensor 4c2f443b…)
type     source                value  label_eligible  flags
NORMAL   JPS_NATIONAL_LISTING  0.00   false
AMARAN   JPS_NATIONAL_LISTING  2.50   true            THRESHOLD_PROVENANCE_CONFLICT
AMARAN   JPS_PENANG_PORTAL     2.60   true            THRESHOLD_PROVENANCE_CONFLICT
```

## 9. Licensing handling

JPS content (J1–J3 in `docs/DATA_LICENSING_AND_ACCESS.md`) is **PERMISSION REQUIRED**:

- The real station master (`data/local/station_master/*.csv`) is a complete JPS-derived table
  (IDs, names, coordinates, thresholds). It is written only under `data/local/`, which is
  git-ignored (`.gitignore`: `data/local/`; confirmed with `git check-ignore`). Rebuild it with
  `.venv\Scripts\python.exe scripts\build_station_master.py`.
- Tracked content is limited to the schema, the code, the validation rules, the synthetic
  fixtures and the aggregate counts below. The existing tracked inventory CSVs keep the status
  they were given by the licensing review. This task only reads them.
- Tests use the synthetic fixtures. One test reads the tracked inventories and asserts aggregate
  counts only. No test reads `data/local/`.

## 10. Validation results (real data, local build 2026-09-24)

Aggregate counts from `scripts/build_station_master.py` on the tracked inputs:

| Measure | Count |
|---|---|
| Canonical sites | 65 |
| Rainfall sensors / water-level sensors | 56 / 22 |
| Multi-sensor sites (RF + WL) | 13 (all 13 shared `jps_internal_id`s passed every merge check) |
| Rainfall-only / water-level-only sites | 43 / 9 |
| Ambiguous mappings (review sites) | 0 |
| Sites missing coordinates | 0 |
| Duplicate `jps_internal_id` within a listing / feed key collisions | 0 / 0 |
| Sensors with `DUPLICATE_DISPLAY_ID` | 4 (2 display IDs × 2 RF rows) |
| Sensors with `MISSING_DISPLAY_ID` | 4 (3 "No Data", 1 blank) |
| `WHITESPACE_NORMALISED_SOURCE_ID` sites | 1 |
| `CRS_INFERRED` sites | 65 |
| `MISSING_BASIN` sites | 0 |
| `SENSOR_TYPES_SOURCE_MISMATCH` sites | 6 (the feed lists RF,WL but only one listing contains the ID; no sensor was invented) |
| `COLOCATED_WITH_OTHER_SITE` sites | 2 (one shared point, not merged) |
| Sensors with a 15-min expected listing interval ("(F2)") | 52 of 78 |
| Threshold records | 103 = national 88 (22 × NORMAL/WASPADA/AMARAN/BAHAYA) + Penang portal 15 (5 × WASPADA/AMARAN/BAHAYA) |
| Label-eligible threshold records | 81 (all 22 NORMAL excluded) |
| `THRESHOLD_PROVENANCE_CONFLICT` | 14 records: 3 sensors, 7 sensor-type pairs; matches the 3 of 5 stations reported in `GIS_FLOOD_DATASETS.md` |

## 11. Limitations

- There is one capture per source, so `fg_first_seen_at`/`fg_last_verified_at` reflect this
  snapshot only. Carrying `fg_first_seen_at` forward across rebuilds, and detecting reused IDs
  by comparing attributes, are not implemented.
- `jps_internal_id` uniqueness and stability are observed, not documented by JPS.
- Coordinates have no version history and no declared CRS.
- The 15-min interval rests on one 23-minute live sample and on a name marker ("(F2)").
- Penang-portal thresholds exist for 5 stations only, from one probe recorded in a doc table.
- Colocated IDs and sensor-type mismatches are flagged but not resolved. They need JPS
  confirmation.

## 12. Observation station-ID normalisation (derived layer)

Status: implemented 2026-09-24 (Phase 2 "Normalize station IDs"). Code:
`src/floodguard/preprocessing/station_ids.py`, batch script `scripts/normalize_station_ids.py`,
tests `tests/test_station_id_normalization.py`. Schema version `station_id_normalization/v1`.
Fields: `docs/04_DATA_DICTIONARY.md` section 1d.

**Architecture decision.** Raw ingestion already resolves `fg_sensor_id` at ingest time
(`floodguard.ingestion.station_mapping`) and quarantines unmapped rows. The derived layer does
**both**: it (a) re-resolves every record from its preserved source IDs against the station
master given on the command line, treating the raw-time `fg_sensor_id` as provisional (as the
timestamp layer re-parses raw time text), and (b) compares the result with the raw-time value.
There is **one resolver**: `SensorMapper.lookup` in `station_mapping.py`. The raw layer's
`SensorMapper.resolve` is a thin view of it (ID or quarantine reason), so the two layers cannot
drift apart; no second lookup or ID-generation scheme exists. Why re-resolve instead of copying:
the station master is rebuilt as JPS metadata changes, re-resolution lets old raw batches
(including quarantined rows) pick up sensors added later without touching the raw store, and it
adds `fg_site_id`, which the raw record does not carry.

Because `fg_sensor_id` is a pure function of (source, key, sensor type), the raw and derived
values can differ only by one side being null (the master gained or lost that sensor; counted as
`raw_mapping_changed`). Two different non-null IDs mean a recipe change or a bug: the script
rejects the batch (exit 2) and writes nothing.

**Mapping policy.**

- Key: `source` + `normalise_source_id(jps_internal_id)` (outer whitespace stripped, case kept)
  + `sensor_type` from the adapter. Never the name, coordinates, display ID, value or time.
- `fg_site_id` is read from the master's `sensors.csv`, not re-derived, so review sites
  (section 4) stay separate. It must equal the key's canonical or review site ID.
- Raw `jps_internal_id` and `jps_display_station_id` are copied exactly; `lookup_key` is a
  separate field. The display ID is carried through and never looked up (duplicates, blanks and
  "No Data" do not affect mapping).
- Records are never dropped, merged or deduplicated, and no ID is ever invented.

**Statuses** (`station_id_mapping_status`; every non-`MAPPED` row has a `mapping_reason`):

| Status | When |
|---|---|
| `MAPPED` | (source, key, type) is in the master: exactly one `fg_site_id` + `fg_sensor_id` |
| `UNMAPPED` | no sensor of any type for (source, key), e.g. a non-Penang or new station |
| `SENSOR_TYPE_MISMATCH` | the key exists, but not for this sensor type (e.g. a rainfall row for a WL-only site). Kept separate from `UNMAPPED` because it points at listing/type drift, not an unknown station |
| `INVALID_SOURCE_ID` | internal ID absent, blank, whitespace-only or with inner whitespace |
| `INVALID_SENSOR_TYPE` | sensor type absent or not `RAINFALL`/`WATER_LEVEL` (adapter contract violation; the raw layer raises instead) |

Precedence: source ID, then sensor type, then lookup.

**No `AMBIGUOUS` status.** A master inconsistency is a hard error at load time
(`StationMappingError`), never a per-record status: a `fg_sensor_id` that does not re-derive (e.g.
a rainfall row carrying a WL sensor's ID), a `fg_site_id` that is not the key's canonical or review
site (which also rules out two sensors of one type at one site), a duplicate (source, key, type)
including whitespace variants of one key, a wrong schema version or a missing column. A master
that fails any check could mis-map every record, so nothing is mapped from it.

**Canonical observation identity** is `(source, fg_sensor_id, observation_time)` (observation time
from the timestamp layer). The source-level pre-mapping identity is unchanged:
`(source, jps_internal_id stripped, measurement_type, observation time)`. This layer performs no
deduplication; overlap between listing polls is left to the validation layer.

**Batch script.** `scripts/normalize_station_ids.py --records <raw_root>/.../<sha256>.records.jsonl`
(or `.quarantine.jsonl`) verifies the file against its `SUCCEEDED` manifest entry, loads the station
master (default `data/local/station_master/sensors.csv`; `--station-master` overrides it) and writes
`data/interim/station_ids/v1/<same relative path>/<sha256>[.quarantine].station_ids.jsonl`
(git-ignored), write-once via `floodguard.ingestion.storage`. Sources without a station master
(data.gov.my forecasts) are rejected. Rows join back to raw records and timestamp rows by
`ingestion_batch_id` + `source_row_index`. The step is not chained after timestamp normalisation:
timestamp rows do not carry `sensor_type` or the display ID, so both derived files are built
independently from the same raw records.

**Local run (2026-09-24, temporary directory only, nothing tracked).** The 8 local JPS captures were
ingested into a temporary raw root with the local master, then normalised: 16 derived files
(records + quarantine), 1,023 rows, all `MAPPED` (112 rainfall-listing, 44 water-level-listing,
289 rainfall-history, 578 water-level-history); 0 raw/derived disagreements; 65 distinct sites and
78 sensors; 13 sites with both RF and WL rows; 2 rows with a whitespace-normalised internal ID; 8
rows with a blank or "No Data" display ID; raw files, captures and master unchanged (hashes).

**Limitations.**

- The output is tied to one master file (`station_master_origin` = file name + SHA-256 prefix). A
  rebuilt master produces different bytes, so rerunning into the same output root is refused; use
  a new output root. Choosing the master version per derived file is left to the pipeline task.
- Only JPS has a station master; other sources are out of scope for this layer.
- Reuse of a JPS internal ID for a different physical site is not detectable here (section 3).
