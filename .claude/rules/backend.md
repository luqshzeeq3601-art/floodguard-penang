---
paths:
  - "src/floodguard/api/**/*.py"
  - "src/floodguard/database/**/*.py"
---

# Backend Rules

- Use typed Pydantic schemas.
- Use explicit response models.
- Keep routes thin.
- Put business logic in services/domain modules.
- Do not duplicate feature/model logic.
- Use migrations for schema changes.
- Add health and readiness endpoints.
- Use structured logging.
- Never expose secrets or internal stack traces.
- Prediction responses must include model version and horizon.
