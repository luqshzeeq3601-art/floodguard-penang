# Skill Routing

Load the minimum skill set required for the task.

## Precedence

1. FloodGuard correctness/safety rules.
2. Primary domain skill.
3. Workflow methodology.
4. Graphify if broad codebase context is needed.
5. Ponytail for minimal implementation.
6. Caveman for concise communication.

## Task Matrix

| Task | Primary | Secondary if needed |
|---|---|---|
| ML training/evaluation | machine-learning-ops | scikit-learn / Superpowers |
| Time-series/statistical baseline | statsmodels | machine-learning-ops |
| Forecast benchmark | timesfm-forecasting | ml-engineer |
| Feature engineering | machine-learning-ops | scikit-learn |
| Data ingestion / ETL | data-engineering | Graphify |
| Streaming | data-engineering | observability-monitoring |
| GIS/PostGIS | geopandas / geomaster | data-engineering |
| FastAPI | python-development / fastapi-pro | unit-testing |
| Streamlit | Python + project Streamlit rule | ML skill for page |
| React | JS/TS/frontend skill | E2E testing |
| Tests | unit-testing | Superpowers TDD |
| Debugging | Superpowers systematic-debugging | Graphify |
| Monitoring | observability-monitoring | production-reviewer |
| Deployment | cloud/infrastructure | production-reviewer |
| Security | official security/review plugin | production-reviewer |
| PR review | official PR review toolkit | Graphify |
| Large plan | Superpowers writing-plans | Graphify |
| Multi-step implementation | Superpowers executing/subagent workflow | Ponytail |

## Skill Budget

Normal task:

- one primary skill;
- zero or one secondary workflow;
- zero or one reviewer (independent reviewer when production-critical);
- Graphify only when required;
- efficiency tools only when useful.

"Official review" means Claude Code's built-in `/code-review` and `/security-review`; no extra review plugin is installed.

Installed stack and status: `docs/15_CLAUDE_SKILLS_SETUP.md`.

Do not activate multiple broad skill packs with overlapping instructions.
