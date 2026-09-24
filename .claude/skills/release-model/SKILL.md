---
name: release-model
description: Gate promotion of a validated FloodGuard model into staging/production.
---

# Release Model

Require:

1. traceable MLflow run;
2. dataset/feature versions;
3. test-set evaluation;
4. baseline comparison;
5. leakage audit;
6. model card;
7. artifact load test;
8. API schema compatibility;
9. latency check;
10. fallback/rollback model;
11. monitoring support.

Do not promote only because accuracy improved.
