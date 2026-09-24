# METMalaysia (data.gov.my weather API) test fixtures (provenance)

Both files are REAL responses captured 2026-09-24T03:29:26Z (11:29:26 +08:00) with an
unauthenticated `GET` (HTTP 200, `application/json`). No values were invented. Synthetic cases are
built inside the tests by mutating these payloads and are labelled `synthetic` there.

| File | Source request | Trimming |
|---|---|---|
| `weather_forecast_trimmed_20260924T112926+0800.json` | `https://api.data.gov.my/weather/forecast` (898,859 B, 3,080 records = 440 locations x 7 dates) | kept the 21 records for `St003` Pulau Pinang, `Ds012` Timur Laut (Penang) and `Ds001` Langkawi (non-Penang control), in source order, values verbatim; JSON re-serialised (indent 1) |
| `weather_warning_20260924T112926+0800.json` | `https://api.data.gov.my/weather/warning` | none: full body, byte-for-byte (7,962 B, 4 records) |

Evidence and context: `data/metadata/metmalaysia/ACCESS.md`.
