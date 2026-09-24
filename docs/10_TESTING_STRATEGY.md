# Testing Strategy

## 1. Testing Pyramid

### Unit

Test:

- feature functions;
- validators;
- label logic;
- threshold logic;
- API schemas;
- utility functions.

### Data Tests

Test:

- schema;
- units;
- duplicates;
- missingness rules;
- timestamps;
- station IDs;
- ranges.

### Temporal Leakage Tests

Explicitly test:

- lag direction;
- rolling windows;
- target construction;
- preprocessing fit boundaries;
- timestamp alignment.

### Model Tests

Test:

- artifact load;
- deterministic schema;
- prediction range;
- missing-feature behavior;
- basic invariance/directional behavior where justified.

### Integration

Test:

- ingestion -> validation;
- database -> feature build;
- model -> API;
- API -> prediction storage.

### E2E

Test critical workflow:

```text
replayed observation
      ↓
ingestion
      ↓
validation
      ↓
features
      ↓
prediction
      ↓
database
      ↓
API/dashboard response
```

## 2. Regression Tests

Add a regression test for every production bug with a deterministic reproduction.

## 3. CI Gates

At minimum:

```text
ruff
mypy relevant modules
pytest
API smoke test
Docker build
```

## 4. Model Metric Regression

Do not fail every CI build because a stochastic metric changes slightly.

Use:

- fixed seeds;
- stable fixtures;
- tolerance;
- dedicated scheduled/full model validation.

## 5. Test Data

Synthetic fixtures are allowed for software tests.

They must be explicitly marked synthetic.

Synthetic test data must never be presented as real Penang flood evidence.
