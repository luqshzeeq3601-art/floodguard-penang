# Unit Policy

Status: implemented 2026-09-24 (Phase 2 "Validate units"). Code:
`src/floodguard/preprocessing/units.py`, batch script `scripts/validate_units.py`, tests
`tests/test_unit_validation.py`. Schema `unit_validation/v1`, policy `unit_policy/v1`.

Unit validation is a **derived layer**. It reads raw records (accepted or quarantined) and writes a
separate file; payloads, records, quarantine files and the manifest are never modified. It does not
convert units, apply range bounds, impute, deduplicate or drop anything. Zero stays `0.0`.

The module sits in `preprocessing/` next to the timestamp and station-ID layers: each derived step
reads the raw records independently and joins on `ingestion_batch_id` + `source_row_index`
(`docs/03_DATA_PLAN.md` section 4). Sensor-type consistency uses the raw record's `sensor_type`
(set by the adapter); the station-ID layer separately checks it against the station master.

## 1. Terms

| Term | Meaning |
|---|---|
| `source_unit_raw` | Unit text printed in the payload's own field label (only the water-level listing, `Aras Air (m)`). |
| `raw_record_unit` | Unit the ingestion adapter wrote into the raw record (`unit`), checked for the primary value only. |
| `unit_provenance` | Where the unit comes from: `IN_PAYLOAD` (field label), `OFFICIAL_UI_OR_DOCS` (official graph-page labels or API documentation), `INFERRED` (reasoned from values). |
| `semantics_status` | `VERIFIED`: what the number measures (and over which period) is supported by evidence. `UNVERIFIED`: it is not. |
| `canonical_unit` | The unit FloodGuard uses downstream: `mm`, `m`, `°C`. |

Rules enforced when the registry is loaded (`check_policy`): a promoted field must be `VERIFIED`
and never `INFERRED`; `IN_PAYLOAD` entries must capture the unit from the label; a field cannot be
both promoted and excluded; thresholds must carry a category.

## 2. Promoted fields (`UNIT_POLICIES`)

| Source / dataset | Field | measurement_type | Unit | Provenance | Evidence |
|---|---|---|---|---|---|
| JPS `rainfall_listing` | `Jumlah 1 Jam(Terkini)` | `RAINFALL_1H_TOTAL` | mm | OFFICIAL_UI_OR_DOCS | Unit: graph-page labels "Data Hujan (mm)", axis "Hujan (mm)" (`data/metadata/jps/HISTORICAL_AVAILABILITY.md`, Rainfall "Units"). The listing header prints no unit. The period (1 hour) is stated in the header; whether it is a trailing or a clock-hour window was not observed (`LIVE_ACCESS.md`, dry period) |
| JPS `rainfall_history` | `raw` | `RAINFALL_INTERVAL` | mm | OFFICIAL_UI_OR_DOCS | Same unit labels; `raw` = rain in the 5-min interval ending at `dt` (equals the `cyearly` step in every checked pair, high confidence; HISTORICAL_AVAILABILITY.md Rainfall "Semantics") |
| JPS `water_level_listing` | `Aras Air ({unit})(Graf)`, published `Aras Air (m)(Graf)` | `WATER_LEVEL` | m | IN_PAYLOAD | Header "Aras Air (m)" (`data/metadata/jps/README.md`, water-level inventory) |
| JPS `water_level_history` | `final` | `WATER_LEVEL` | m | OFFICIAL_UI_OR_DOCS | Graph-page labels "Aras Air (m)"; the official page plots `final` (HISTORICAL_AVAILABILITY.md Water Level "Units"/"Fields") |
| JPS `water_level_listing` | `Tahap Nilai Ambang Normal/Waspada/Amaran/Bahaya` | `WATER_LEVEL_THRESHOLD` | m | OFFICIAL_UI_OR_DOCS | Graph-page tooltip "Normal: …m Waspada: …m Amaran: …m Bahaya: …m" (HISTORICAL_AVAILABILITY.md Water Level "Units") |
| JPS `water_level_history` | `info.normal/alert/warning/danger` | `WATER_LEVEL_THRESHOLD` | m | OFFICIAL_UI_OR_DOCS | Same tooltip; key-to-category from the listing markup `<th id='alert'>Waspada</th>`, `id='warning'` Amaran, `id='danger'` Bahaya |
| data.gov.my `weather_forecast` | `min_temp`, `max_temp` | `FORECAST_TEMPERATURE_MIN/MAX` | °C | OFFICIAL_UI_OR_DOCS | `data/metadata/metmalaysia/ACCESS.md` section 1A "Units": integers in °C **[doc]** |

Threshold rows carry `threshold_category` (`NORMAL`, `WASPADA`, `AMARAN`, `BAHAYA`, the station
master's `ThresholdType`) separately from the unit, and keep the raw
`threshold_temporal_scope`: listing thresholds are `CURRENT_AT_RETRIEVAL`; history thresholds are
`CURRENT_NOT_HISTORICAL` (today's values returned for any window), never historical values.

Accepted source representations are only those seen: `mm`, `m`, `°C` (outer whitespace ignored).
No case or spelling variants are accepted, and no conversion exists because each verified field
has exactly one unit.

## 3. Excluded fields (`EXCLUDED_FIELDS`)

Reported as `UNKNOWN_MEASUREMENT_SEMANTICS` with no measurement type, no canonical unit and no
`parsed_value`:

| Source / dataset | Field | Reason |
|---|---|---|
| JPS `rainfall_history` | `clean` | Depends on the request `datafreq` (5-min step or trailing 15-min sum) |
| | `chourly`, `c15min` | Meaning unknown (equalled `clean` in inspected rows) |
| | `tdaily` | Meaning unknown (`0` in every inspected row) |
| | `cdaily` | Running daily total; one unexplained window; derivable from `raw` |
| | `cyearly` | Running yearly total; not promoted in v1 (derivable from `raw`) |
| | `info.light/moderate/heavy/veryheavy` | Rainfall thresholds: unit and accumulation period not labelled |
| JPS `rainfall_listing` | `Taburan Hujan Harian <date>` | Daily totals: day boundary not verified for the listing |
| | `Taburan Hujan dari Tengah Malam (<date>)` | Since-midnight total: semantics not verified |
| JPS `water_level_history` | `raw`, `ecm`, `clean` | Pre-QC / ECM / clean semantics undocumented |
| data.gov.my `weather_forecast` | `summary_forecast` (primary value) | Categorical text, not a numeric measurement |

Other fields (IDs, names, times, `severity`, `*_forecast`, `summary_when`, location) are not
unit-validated and produce no row.

## 4. Output row and statuses

One row per validated field: the record's primary value (`PRIMARY_VALUE`), each published
threshold (`THRESHOLD`) and any other field named in section 2 or 3 (`SOURCE_FIELD`). Each row
copies the join keys, `source_station_id`, `sensor_type` and `source_time_raw` exactly.

`unit_validation_status` (checked in this order; first failure wins):

| Status | Fires when |
|---|---|
| `UNKNOWN_MEASUREMENT_SEMANTICS` | The field is excluded (section 3) or not in the policy at all |
| `SENSOR_TYPE_MISMATCH` | The record's `sensor_type` differs from the entry's (rainfall field on a water-level sensor, water-level threshold on a rainfall sensor, sensor type on a forecast). A dedicated state because the unit is not what is wrong |
| `MISSING_UNIT` | An `IN_PAYLOAD` field's label carries no unit text (e.g. `Aras Air ()(Graf)`) |
| `UNIT_MISMATCH` | The label unit or `raw_record_unit` is a known unit of another measurement (`mm` on water level, `m` on rainfall) |
| `UNKNOWN_UNIT` | The label unit or `raw_record_unit` is not an accepted representation (e.g. `ft`, `cm`) |
| `VALID` | Otherwise. A field with `OFFICIAL_UI_OR_DOCS` provenance and no unit in the payload is `VALID` |

`value_parse_status` is independent of the unit status:

| Status | Values |
|---|---|
| `NUMERIC` | Decimal text after trimming outer whitespace (`" 1.5"`, `"0.0"`, `"-0.31"`); `-9999` excluded |
| `SOURCE_MARKER` | `-9999` (also compared numerically, e.g. `-9999.00`), `ERROR`, `Tiada Data` |
| `EMPTY` | JSON null, absent, blank or whitespace-only |
| `NON_NUMERIC` | Anything else (`"1,2"`, `"abc"`, `"nan"`, `"inf"`, `"1_0"`) |

`parsed_value` is set only when the unit is `VALID` **and** the value is `NUMERIC`; `value_raw`
always keeps the exact text. Negative water levels are kept (observed upstream); range checks
belong to the quality-flag step.

## 5. Derived output

`scripts/validate_units.py --records <raw>/<...>/<sha256>.records.jsonl` (or `.quarantine.jsonl`)
checks the file against its SUCCEEDED manifest hash and writes
`data/interim/units/v1/<same relative path>/<sha256>[.quarantine].units.jsonl` (git-ignored),
write-once via `floodguard.ingestion.storage`. It prints status, measurement-type, value-status and
not-promoted-field counts. Exit 0 written or already present, 2 rejected.

Local check (2026-09-24, scratch output only): the 9 local JPS/data.gov.my captures (1,219 raw
records) gave 9,507 rows: 3,903 `VALID` (289 `RAINFALL_INTERVAL`, 112 `RAINFALL_1H_TOTAL`, 622
`WATER_LEVEL`, 2,488 `WATER_LEVEL_THRESHOLD`, 196 + 196 forecast temperatures; 424 of them
`SOURCE_MARKER` values) and 5,604 `UNKNOWN_MEASUREMENT_SEMANTICS`; no unit or sensor-type
failures. Two runs were byte-identical and the raw store was unchanged.

## 6. Limitations

- `RAINFALL_1H_TOTAL`: trailing vs clock-hour window not verified (no rain during the live probe).
- `RAINFALL_INTERVAL`: when grid rows are absent, whether the next `raw` covers the gap is unknown.
- Listing threshold unit rests on the graph-page tooltip plus one station whose listing and graph
  JSON values match; the listing header itself has no unit.
- History thresholds repeat on every history row (as in the raw record) and are current values.
- A new, unregistered numeric source field is not reported here (schema drift is the raw layer's
  job); only the primary value, thresholds and registered fields are validated.
- Forecast temperatures have no issue time (`ACCESS.md`); that is a temporal, not a unit, caveat.
