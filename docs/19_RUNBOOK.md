# Production Runbook

## 1. Live Data Stops Updating

Check:

1. source availability;
2. authentication/rate limit;
3. ingestion logs;
4. station-specific failure;
5. timestamp parsing;
6. database write;
7. freshness metric.

Do not impute stale live data indefinitely.

## 2. Prediction Endpoint Fails

Check:

1. readiness;
2. model artifact availability;
3. feature schema;
4. database connectivity;
5. latest valid observation;
6. logs/traces.

## 3. Model Artifact Cannot Load

- mark service unready;
- do not return fabricated/default prediction;
- use explicit rollback policy if available;
- record incident.

## 4. Data Schema Changes

- retain raw payload;
- fail/flag validation;
- update contract intentionally;
- add regression fixture;
- rerun downstream tests.

## 5. Sudden Prediction Distribution Shift

Investigate:

- source data;
- missingness;
- sensor behavior;
- weather event;
- feature pipeline change;
- model version.

Do not automatically conclude model drift.

## 6. False-Negative Event

Perform event review:

- raw inputs;
- data quality;
- feature values;
- probability;
- threshold;
- model version;
- nearby stations;
- label correctness.

Create a reproducible case.
