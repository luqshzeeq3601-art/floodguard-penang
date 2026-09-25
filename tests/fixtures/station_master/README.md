# Station master test fixtures: SYNTHETIC

Every file in this directory is **synthetic**. IDs (`SYN…`, `999…`), names ("Synthetic …"),
coordinates, basins ("Sungai Sintetik …"), thresholds, timestamps (year 2000) and URLs
(`example.invalid`) are invented. They do not describe any real JPS station. District names are
the five real Penang district names, used only as category values.

| File | Role |
|---|---|
| `synthetic_rainfall.csv` | Rainfall listing input (same column names as `data/metadata/jps/penang_rainfall_stations.csv`, subset) |
| `synthetic_water_level.csv` | Water-level listing input (subset of `penang_water_level_stations.csv` columns) |
| `synthetic_coordinates.csv` | Map-feed coordinate input (columns of `data/metadata/gis/penang_station_coordinates_jps.csv`) |
| `synthetic_threshold_comparison.md` | National vs Penang-portal threshold table in the row format of `GIS_FLOOD_DATASETS.md` section 5 |
| `expected/sites.csv`, `expected/sensors.csv`, `expected/thresholds.csv` | Golden output of `scripts/build_station_master.py` on the inputs above; also the schema examples for `docs/STATION_MASTER_DESIGN.md` |

Cases covered (source key → expected result):

| Key | Case | Result |
|---|---|---|
| `SYN001` | RF + WL, same district and basin as feed | 1 site, 2 sensors; Penang-portal Amaran differs → conflict flag |
| `SYN002` | Two feed records normalise to the same key | no coordinates; `SOURCE_ID_COLLISION` |
| `SYN002`, `SYN003` | Same RF display ID | `DUPLICATE_DISPLAY_ID` on both sensors |
| `SYN004` | Display "No Data"; feed basin blank | `MISSING_DISPLAY_ID`; `MISSING_BASIN` |
| `" SYN005_"` | Leading space in listing ID; blank display ID | joins feed `SYN005_`; `WHITESPACE_NORMALISED_SOURCE_ID`; `MISSING_DISPLAY_ID` |
| `SYN006` | WL only, feed says RF,WL | `SENSOR_TYPES_SOURCE_MISMATCH` |
| `SYN007` | RF + WL, WL district differs from feed | 2 sites (canonical RF, review WL), both `AMBIGUOUS_SITE_MAPPING` |
| `SYN008` | No feed record | `MISSING_COORDINATES` |
| `SYN009`, `SYN010` | Different keys, identical coordinates | not merged; `COLOCATED_WITH_OTHER_SITE` |
| `SYN011` | RF + WL, no feed record | 2 review sites, `AMBIGUOUS_SITE_MAPPING` |

Regenerate the golden files (only when the schema changes intentionally):

```text
.venv\Scripts\python.exe scripts\build_station_master.py --rainfall tests\fixtures\station_master\synthetic_rainfall.csv --water-level tests\fixtures\station_master\synthetic_water_level.csv --coordinates tests\fixtures\station_master\synthetic_coordinates.csv --penang-threshold-doc tests\fixtures\station_master\synthetic_threshold_comparison.md --output-dir tests\fixtures\station_master\expected
```
