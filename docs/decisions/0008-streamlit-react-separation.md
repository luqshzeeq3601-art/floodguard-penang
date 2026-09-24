# ADR-0008: Separate Streamlit and React Responsibilities

## Status

Accepted

## Context

FloodGuard has two audiences: ML engineers and analysts who need fast, flexible analysis tools, and operational users who need a clear, reliable interface.

## Decision

**Streamlit** is the internal ML/analytics workspace: EDA, live station analysis, prediction testing, model performance, SHAP explanations, data quality, and drift (`docs/08_STREAMLIT_PLAN.md`).

**React/TypeScript** is the operational/public-facing application: map, station status, risk levels, predictions clearly separated from observations, and alert history (`docs/09_FRONTEND_PLAN.md`).

Both consume FastAPI (ADR-0007); neither holds core business logic.

## Alternatives

- **Streamlit only:** one UI stack; limited control over production UX, routing, performance and accessibility for operational users.
- **React only:** one polished UI; every internal analysis view would need full frontend engineering, slowing ML iteration.

## Consequences

Positive:

- ML tooling iterates quickly without affecting the operational UI;
- the operational UI gets production-grade UX.

Trade-off:

- two UI codebases and toolchains to maintain;
- shared views (e.g. station trends) may exist in both, so consistency relies on the shared API.

## Validation

Streamlit pages (Phase 9) and React views (Phase 11) are checked for calling the API rather than importing ML code.

## Date

2026-09-24
