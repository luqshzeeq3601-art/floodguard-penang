# ADR-0009: Scheduled Polling Before Kafka/MQTT

## Status

Accepted

## Context

Live data comes from a modest number of Penang rainfall and water-level stations published by upstream services (JPS, METMalaysia) at intervals measured in minutes. Upstream access methods are not verified yet (Phase 1).

## Decision

Start live ingestion with scheduled polling of the upstream sources. Ingestion must be idempotent, with bounded retries and stale-station detection.

Introduce Kafka or MQTT only if measured source frequency, throughput, latency, or reliability requirements justify it. That decision is made in Phase 10 ("Decide whether Kafka/MQTT is justified") and recorded as its own ADR.

## Alternatives

- **Kafka from day one:** durable event log and replay; heavy operational overhead for a low data rate.
- **MQTT from day one:** suited to device push; upstream sources are HTTP services, not devices publishing to a broker.
- **Other event-streaming infrastructure:** same overhead without a measured need.

## Consequences

Positive:

- fewer services to run, test, and reproduce locally;
- simple failure handling (retry on the next poll).

Trade-off:

- latency is bounded by the polling interval;
- if data rates or consumers grow, adding a broker later requires refactoring ingestion.

## Validation

Phase 10 measures ingestion latency and staleness. A broker is proposed only if those measurements show polling cannot meet requirements.

## Date

2026-09-24
