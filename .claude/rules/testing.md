---
paths:
  - "tests/**/*"
  - "src/**/*.py"
  - "streamlit_app/**/*.py"
  - "frontend/**/*"
---

# Testing Rules

- Add regression tests for fixed bugs.
- Do not weaken tests to pass CI.
- Critical ML transformations need leakage tests.
- Use synthetic fixtures only when clearly marked.
- Software tests may use small deterministic model fixtures.
- Keep expensive full model training outside normal unit tests.
