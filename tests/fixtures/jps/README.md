# JPS test fixtures (provenance)

All fixtures are trimmed copies of REAL responses from https://publicinfobanjir.water.gov.my/
captured 2026-09-24 (+08:00). No values were invented. Synthetic cases are built inside the tests
by mutating these files and are labelled `synthetic` there.

| File | Source request | Trimming |
|---|---|---|
| `searchresultrainfall_PNG_trimmed.html` | rainfall state listing | see header comment in file |
| `data_hujan_PNG_page_trimmed.html` | rainfall state page | see header comment in file |
| `aras_air_data_PNG_trimmed.html` | water-level state listing | see header comment in file |
| `data_paras_air_PNG_page_trimmed.html` | water-level state page | see header comment in file |
| `history_rainfall_27608_20260918_trimmed.json` | `searchresultrainfalldthourlylead.php?extra=&station=27608&from=18/09/2026 00:00&to=19/09/2026 00:00&datafreq=5` | rows 18/09/2026 00:00–05:00 (61 of 289) kept verbatim; `info.count` set to 61; JSON re-serialized |
| `history_water_level_26460_20260923_trimmed.json` | `searchresultwaterleveldtlead.php?station=26460&from=23/09/2026 00:00&to=24/09/2026 00:00&datafreq=5` | rows 12:00–12:45 kept verbatim (first valid reading at 12:25); `info.count` set; re-serialized |
| `history_water_level_27608_20240924_trimmed.json` | same endpoint, `station=27608`, 24/09/2024 | rows 13:45–14:20 (8 of 289) kept verbatim: `ERROR` rows, `SL_NML` rows, blank-severity `-9999` rows; `info.count` set; re-serialized |
| `history_no_result.txt` | rainfall endpoint, `station=27608`, 01/01/2023 | full body, byte-for-byte (24 B) |

Full untrimmed captures are in `data/metadata/jps/raw/`.
