---
name: audit-data
description: Audit FloodGuard datasets before EDA, feature engineering, or training.
---

# Audit Data

1. Identify source and dataset version.
2. Confirm Penang-only station scope.
3. Inspect schema and units.
4. Inspect timestamp timezone and ordering.
5. Measure duplicates.
6. Measure missingness.
7. Detect stale/offline periods.
8. Check valid ranges.
9. Inspect station continuity.
10. Check label availability.
11. Save a data-quality report.
12. Block training if leakage or timestamp integrity is unresolved.

Never fix raw data in place.
