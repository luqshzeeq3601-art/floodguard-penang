---
paths:
  - "src/floodguard/ingestion/**/*.py"
  - "src/floodguard/validation/**/*.py"
  - "src/floodguard/preprocessing/**/*.py"
  - "data/**/*.md"
---

# Data Quality Rules

Preserve raw data.

Validate:

- timestamp;
- station ID;
- unit;
- duplicates;
- valid range;
- missingness;
- freshness;
- schema version.

Never convert missing rainfall to zero without evidence.

Use explicit quality flags.

Every cleaning step must be reproducible.
