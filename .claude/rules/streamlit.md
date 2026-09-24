---
paths:
  - "streamlit_app/**/*.py"
---

# Streamlit Rules

Streamlit is internal ML/analytics UI.

- Call shared services/FastAPI.
- Do not reimplement production ML logic.
- Show data timestamp and quality.
- Label observed vs forecast vs predicted.
- Avoid decorative charts.
- Cache cautiously.
- Prefer operational/analytical value over visual complexity.
- SHAP explanations must not be framed as causal.
