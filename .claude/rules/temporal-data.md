---
paths:
  - "src/floodguard/features/**/*.py"
  - "src/floodguard/preprocessing/**/*.py"
  - "src/floodguard/training/**/*.py"
  - "notebooks/**/*.ipynb"
---

# Temporal Data Rules

- Rolling features must be backward-looking.
- No centered rolling windows.
- No interpolation from future observations unless explicitly excluded from production features.
- Do not fit preprocessing on validation/test data.
- Split chronologically.
- Prefer walk-forward validation where practical.
- Verify forecast issue time versus forecast valid time.
- Label horizons must be explicit.
- Add tests for leakage-prone transformations.
