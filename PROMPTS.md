# Claude Code Starter Prompts

## Start a New Session

```text
Read CLAUDE.md, AGENTS.md, TASKS.md, and the applicable .claude rules.

Determine the current incomplete project phase and dependencies.

Use only the skills required for this task. Prefer Graphify over broad file reading when the task spans modules. Use Ponytail to avoid over-engineering and Caveman lite for concise updates.

Do not fabricate data or metrics. Do not introduce temporal leakage.

Implement the next logically unblocked task, verify it, update relevant documentation/TASKS.md, and report Result / Changed / Verification / Metrics / Remaining.
```

## Data Phase

```text
Use the data-engineer agent and audit-data skill.

Inventory and validate the Penang flood-data source for this phase. Preserve raw data, document schema/timestamps/units/access constraints, implement reproducible ingestion and data-quality checks, and do not train a model until the data gate passes.
```

## ML Phase

```text
Use the ml-engineer agent and applicable ML skills.

Read the approved dataset, feature, label, and temporal-validation definitions. Establish the required baseline first, train the current candidate model, log the experiment, evaluate with recall/false-negative rate/PR-AUC/F1/calibration/latency, and perform false-negative analysis. Do not inspect the final test set repeatedly.
```

## Production Review

```text
Use ml-reviewer and production-reviewer independently.

Review only the relevant changes. Prioritize temporal leakage, data integrity, actual production bugs, reliability, observability, and security. Return high-confidence findings with file/line evidence. Do not create noisy speculative findings.
```
