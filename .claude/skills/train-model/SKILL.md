---
name: train-model
description: Train a FloodGuard model reproducibly using the approved temporal methodology.
---

# Train Model

1. Run `audit-data`.
2. Record dataset/feature/label versions.
3. Confirm temporal split.
4. Run baseline first.
5. Train selected candidate.
6. Log hyperparameters, seed, code commit, and metrics.
7. Save artifact and preprocessing pipeline.
8. Evaluate validation only.
9. Do not inspect final test repeatedly.
10. Register as candidate only after checks pass.
