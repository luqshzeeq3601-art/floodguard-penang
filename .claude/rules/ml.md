---
paths:
  - "src/floodguard/models/**/*.py"
  - "src/floodguard/training/**/*.py"
  - "src/floodguard/features/**/*.py"
  - "pipelines/training_pipeline.py"
---

# ML Rules

- Establish baseline before complex model.
- Use one fixed temporal evaluation protocol for fair comparison.
- Record dataset, feature, and label versions.
- Never tune on final test data.
- Prioritize recall, false-negative rate, PR-AUC, F1, calibration, latency.
- Accuracy is not sufficient for imbalanced flood events.
- Do not introduce deep learning without evidence.
- Log experiments.
- Add error analysis for false negatives.
- Never report targets as achieved metrics.
