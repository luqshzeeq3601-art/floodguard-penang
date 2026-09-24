# ADR-0003: PostgreSQL + PostGIS as the Primary Operational Database

## Status

Accepted

## Context

FloodGuard stores relational station metadata, time-stamped rainfall/water-level observations with quality flags, prediction history, model version metadata, and alert history. Geospatial context (station locations, basins, historical flood areas) is a first-class requirement (`docs/02_ARCHITECTURE.md` §7, `AGENTS.md` §19).

## Decision

Use PostgreSQL with the PostGIS extension as the primary operational database. Schema changes go through migrations. Large model binaries are stored outside the database.

The local baseline is the `db` service in `compose.yaml` (`postgis/postgis:17-3.5`).

## Alternatives

- **SQLite (+ SpatiaLite):** zero setup; weaker concurrent writes and not representative of a deployed service.
- **PostgreSQL without PostGIS:** simpler image; spatial queries would move into application code or a separate GIS store.
- **Dedicated time-series database (e.g. InfluxDB):** strong for high-rate metrics; adds a second datastore for relational and spatial data at FloodGuard's expected low data rate.
- **Document database:** flexible payloads; weaker relational integrity for stations, predictions and alerts.

## Consequences

Positive:

- relational integrity, spatial queries, and time-indexed observations in one store;
- widely available as a managed cloud service.

Trade-off:

- requires a running database service for integration tests and local development;
- very high-rate streaming data may later need partitioning or an extension such as TimescaleDB (not decided).

## Validation

Compose configuration validates and the image tag exists on Docker Hub. **Runtime verification (container health, connectivity, PostGIS query) is BLOCKED** until the Docker engine can run (see `TASKS.md`). This ADR records the architectural choice only.

## Date

2026-09-24
