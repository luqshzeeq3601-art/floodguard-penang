# ADR-0007: FastAPI as the Shared Service Boundary

## Status

Accepted

## Context

Predictions, station data, and monitoring results are consumed by Streamlit, React, and alerting. If each consumer imported ML code directly, prediction and business logic would be duplicated and drift apart.

## Decision

```text
ML / services (src/floodguard)
            ↓
         FastAPI
        ↙      ↘
  Streamlit    React
```

- FastAPI is the shared service contract for predictions, stations, observations, model metadata, and monitoring.
- React consumes FastAPI only. Streamlit calls FastAPI or shared service functions and does not re-implement core logic.
- Responses use Pydantic models and include model-version metadata; `/health` and `/ready` endpoints are required (`AGENTS.md` §18).
- The FastAPI dependency is deferred until the backend phase (Phase 8); it is not installed yet.

## Alternatives

- **Each UI imports ML code directly:** fewer moving parts early; duplicated logic and no single contract.
- **Django / Flask:** mature frameworks; FastAPI's typed Pydantic contracts and async support fit the API-only role more directly.
- **GraphQL gateway:** flexible queries; more machinery than a small set of REST endpoints needs.

## Consequences

Positive:

- one tested contract for all consumers;
- presentation layers can change without touching model code.

Trade-off:

- an extra network hop and a service to run, even for internal tools;
- API versioning must be managed as consumers grow.

## Validation

Phase 8 delivers `/health`, `/ready`, and prediction endpoints with API tests. Latency is measured against the < 500 ms target; that target is not a result.

## Date

2026-09-24
