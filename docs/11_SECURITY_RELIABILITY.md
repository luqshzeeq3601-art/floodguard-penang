# Security and Reliability Plan

## 1. Secrets

Use environment variables.

Never commit:

- API keys;
- passwords;
- cloud credentials;
- tokens.

Provide `.env.example`.

### Configuration Loading

- The process environment is the single source of truth.
- `.env.example` is the contract: active lines are used now; commented lines are planned for the phase noted.
- Locally, `.env` is supplied by the shell or Docker Compose (`env_file`). No dotenv library is used.
- Application code gets one typed settings object (Pydantic) when the first runtime consumer lands (ingestion or API). Until then, no config code exists.
- Outside local development, secrets come from the deployment platform's secrets manager, never from a committed file.

## 2. External Data

Validate all upstream responses.

Assume upstream services can:

- time out;
- return malformed data;
- change schema;
- return duplicate data;
- stop updating.

## 3. Idempotency

An observation should have a stable uniqueness rule such as:

```text
source + station_id + observation_time + measurement_type
```

The actual key depends on source semantics.

## 4. Stale Data

A model should not silently predict on arbitrarily stale sensor data.

Define:

- acceptable age;
- degraded mode;
- no-prediction mode.

## 5. Model Failure

If model artifact fails to load:

- readiness should fail;
- service should not claim valid predictions;
- operator logs should provide actionable error;
- previous validated model may be used only through an explicit fallback policy.

## 6. Database Failure

Define:

- bounded retries;
- clear health/readiness behavior;
- no silent data loss;
- replay/recovery path.

## 7. Alert Delivery Failure

Persist the alert decision before external delivery where possible.

Track:

- pending;
- sent;
- failed;
- retried.

## 8. Rate Limiting

Protect public APIs where relevant.

## 9. Input Validation

Use Pydantic and database constraints.

Do not trust frontend validation alone.

## 10. Dependency Security

Use:

- pinned/locked dependencies;
- dependency scanning;
- minimal runtime images;
- regular updates.

## 11. Reliability Metrics

Possible operational metrics:

- ingestion success rate;
- ingestion lag;
- valid station percentage;
- API p95 latency;
- API error rate;
- prediction failure rate;
- alert delivery success rate.
