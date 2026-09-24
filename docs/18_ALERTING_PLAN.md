# Alerting Plan

## 1. Alert Sources

Alerts may be generated from:

- official threshold state;
- ML risk probability;
- predicted water level;
- stale/offline sensor;
- ingestion failure;
- system failure.

Do not mix operational alerts and flood-risk alerts into one undifferentiated channel.

## 2. Flood Prediction Alert

Suggested payload:

```text
station
observation timestamp
prediction horizon
risk probability
risk category
predicted water level
model version
input quality
top contributing factors
```

## 3. Deduplication

Avoid repeated identical alerts on every poll.

Use:

- station;
- alert type;
- horizon;
- state transition;
- cooldown window.

## 4. Escalation

Example logical states:

```text
NORMAL
ALERT
WARNING
DANGER
```

Actual mapping must align with verified station/source definitions.

## 5. Delivery

Possible portfolio channels:

- Telegram;
- email;
- webhook.

SMS can be added only if useful and available.

## 6. Safety

Do not present FloodGuard as an official emergency-warning authority.

Dashboard and alerts should state source/model context.
