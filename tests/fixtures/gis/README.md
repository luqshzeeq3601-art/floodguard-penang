# GIS source test fixtures (provenance)

All files are REAL responses captured 2026-09-24 with unauthenticated `GET` requests (HTTP 200,
JSON). No values were invented. Synthetic cases are built inside the tests by mutating these
payloads and are labelled `synthetic` there.

| File | Source request (UTC capture) | Trimming |
|---|---|---|
| `jps_latestreadingstrendabc_penang_plus2_trimmed_20260924T041054Z.json` | `https://publicinfobanjir.water.gov.my/wp-content/themes/enlighten/data/latestreadingstrendabc.json` (04:10:54Z, 1,320,015 B, 2,725 records) | kept the first 2 non-Penang records (control) + the 65 records whose `a` is in the JPS inventories, source order; **only keys `a`–`i`** (id, name, lat, lon, district, state, sub-basin, basin, sensor types), values verbatim; live readings, status and trend keys (`j`–`nn`) removed 2026-09-24 (licensing minimisation); JSON re-serialised |
| `pegis_sejarah_banjir_layers_trimmed_20260924T043139Z.json` | `https://pegis.penang.gov.my/arcgis/rest/services/Hosted/Sejarah_Banjir/FeatureServer/layers?f=json` (04:31:39Z, 239,028 B, 27 layers) | kept layers 0, 7, 16, 26; **only `id`, `name`, `type`, `geometryType` and field `name`/`type`** (values verbatim; other layer metadata removed 2026-09-24, licensing minimisation); JSON re-serialised |
| `pegis_sejarah_banjir_counts_20260924T042413Z.json` | `…/Sejarah_Banjir/FeatureServer/query?layerDefs={0..26:"1=1"}&returnCountOnly=true&f=json` (04:24:13Z) | none, byte-for-byte |
| `pegis_sejarah_banjir_layer26_groupby_tarikh_masa_20260924T042428Z.json` | `…/FeatureServer/26/query?groupByFieldsForStatistics=tarikh,masa&outStatistics=[count objectid as n]` (04:24:28Z) | none, byte-for-byte |
| `pegis_sejarah_banjir_layer7_groupby_tarikh_20260924T043429Z.json` | `…/FeatureServer/7/query?groupByFieldsForStatistics=tarikh&outStatistics=[count objectid as n]` (04:34:29Z) | none, byte-for-byte |

Evidence and context: `data/metadata/gis/GIS_FLOOD_DATASETS.md`.

**Rights status.** JPS feed excerpt: PERMISSION REQUIRED (JPS copyright notice). Penang GeoHub
excerpts (layer schema, counts, date statistics): UNKNOWN (item licence fields empty, no portal
terms found). Both are kept, minimised to what the parser tests need, and flagged, not cleared.
Full raw captures stay local (git-ignored) and are listed in
`data/metadata/RAW_EVIDENCE_MANIFEST.csv`. See `docs/DATA_LICENSING_AND_ACCESS.md`.
