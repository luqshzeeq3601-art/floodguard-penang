---
name: check-live-ingestion
description: Validate FloodGuard live-data ingestion health and station freshness.
---

# Check Live Ingestion

For each source/station:

1. latest observation time;
2. ingestion time;
3. lag;
4. duplicate rate;
5. missing intervals;
6. invalid values;
7. schema changes;
8. station status.

Classify:

- healthy;
- delayed;
- stale;
- offline;
- invalid.

Do not feed arbitrarily stale readings to production inference.
