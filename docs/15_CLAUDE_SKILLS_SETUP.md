# Claude Code Skills and Agent Setup

## 1. Goal

Use skills to improve quality while reducing unnecessary context and tokens.

Do not install/load everything.

Use progressive disclosure:

```text
task
 ↓
domain skill
 ↓
workflow skill only if necessary
 ↓
Graphify only if broad repo context is necessary
 ↓
Ponytail simplifies implementation
 ↓
Caveman compresses prose
```

## Installation State (2026-09-24, Claude Code 2.1.278)

Project-scope plugins are declared in `.claude/settings.json`, so they load only in this repository. External skills live beside the FloodGuard local skills in `.claude/skills/`; the local skills (`audit-data`, `train-model`, `evaluate-model`, `release-model`, `check-live-ingestion`, `update-code-graph`) are unchanged and own project policy.

| Item | Status | Source | Method / scope | Verification |
|---|---|---|---|---|
| Ponytail | INSTALLED (pre-existing) | DietrichGebert/ponytail | user skills `~/.claude/skills/ponytail*` | skills discovered in session; plugin not added to avoid a duplicate copy |
| Caveman | INSTALLED (pre-existing) | JuliusBrussee/caveman | user skills `~/.claude/skills/caveman*` | skills discovered in session; use `/caveman lite` |
| Caveman proxy | NOT REQUIRED | JuliusBrussee/caveman | — | skill alone is enough for Phase 0 |
| Graphify | INSTALLED (pre-existing) | Graphify-Labs/graphify | CLI `graphify` + user skill | `graphify --version` → 0.9.57; `.claudeignore` has `graph.json`, `graphify-out/`; no graph built yet (repo too small) |
| Superpowers | INSTALLED | obra/superpowers | `superpowers@claude-plugins-official`, project | `claude plugin list` → 6.4.1 enabled |
| wshobson/agents marketplace | INSTALLED | wshobson/agents | marketplace `claude-code-workflows`, project | added from GitHub |
| machine-learning-ops | INSTALLED | wshobson/agents | plugin, project | 1.2.2 enabled |
| data-engineering | INSTALLED | wshobson/agents | plugin, project | 1.3.2 enabled |
| python-development | INSTALLED | wshobson/agents | plugin, project | 1.2.3 enabled |
| unit-testing | INSTALLED | wshobson/agents | plugin, project | 1.2.1 enabled |
| observability-monitoring | INSTALLED | wshobson/agents | plugin, project | 1.2.3 enabled |
| scikit-learn | INSTALLED | K-Dense-AI/scientific-agent-skills@v2.69.0 | `gh skill install --dir .claude/skills` | discovered as skill; content scanned |
| statsmodels | INSTALLED | same | same | discovered; scanned |
| geopandas | INSTALLED | same | same | discovered; scanned |
| geomaster | INSTALLED | same | same | discovered; scanned |
| timesfm-forecasting | DEFERRED | same | — | optional Phase 6 benchmark only |
| Official review plugins | NOT REQUIRED | anthropics/claude-plugins-official | — | built-in `/code-review` and `/security-review` already cover review |
| Kubernetes / cloud / Kafka / frontend / LLM plugins | DEFERRED | — | — | install when their phase starts |

Notes:

- `gh skill` project scope needs a git repository; `--dir .claude/skills` was used because this folder is not yet one. Update with `gh skill update`.
- K-Dense skills are unverified third-party content. Scan performed: bundled scripts import only stdlib/scikit-learn with no network calls; reference-doc matches were PyTorch `model.eval()` and GDAL `subprocess.run` examples. Review again after updates.
- Ruff excludes `.claude/` so vendored skill scripts are never linted or reformatted.

### Ignore Files

| File | Consumer | Responsibility |
|---|---|---|
| `.gitignore` | Git; also read by Graphify | Secrets, data stages, ML artifacts, caches, `graph.json`, `graphify-out/` |
| `.graphifyignore` | Graphify only | Extra excludes on top of `.gitignore` (can only exclude more). Currently: the 4 vendored K-Dense skill directories |
| `.claudeignore` | Claude context tooling | Generated graph files, ML artifacts, data stages, local env/caches. Not a documented Claude Code 2.1.278 feature; treat as advisory |

Graphify built-in skips already cover `.venv/`, `node_modules/`, `__pycache__/`, tool caches, `build/`, `dist/`, `graphify-out/`, and coverage report dirs, so they are not repeated in `.graphifyignore`.

ML artifact patterns are root-anchored (`/models/`, `/artifacts/`, `/mlruns/`). The unanchored `models/` form also matched the planned source package `src/floodguard/models/`.

Verified 2026-09-24 with `graphify.detect.detect()` (file selection only; nothing extracted): 110 → 60 files and 71,872 → 14,284 words after the changes; Graphify reports `needs_graph: False`, so the first graph build is deferred until the codebase has real module structure.

## 2. Ponytail

Repository:

`https://github.com/DietrichGebert/ponytail`

Purpose:

- YAGNI;
- reuse existing code;
- prefer native/stdlib capabilities;
- reduce unnecessary dependencies and code.

Claude Code:

```text
/plugin marketplace add DietrichGebert/ponytail
```

Then in a separate Claude prompt:

```text
/plugin install ponytail@ponytail
```

Use as an implementation-efficiency layer.

Never let it remove:

- validation;
- security;
- error handling;
- accessibility;
- observability;
- critical tests.

## 3. Caveman

Repository:

`https://github.com/JuliusBrussee/caveman`

Skill install:

```bash
npx skills add JuliusBrussee/caveman -g
```

Recommended normal mode:

```text
/caveman lite
```

Use for:

- concise updates;
- concise summaries;
- output compression.

Do not compress away:

- exact errors;
- paths;
- code;
- commands;
- metrics;
- data-quality warnings;
- security warnings.

The optional proxy may reduce noisy context/tool-output, but evaluate it on real sessions.

## 4. Graphify

Repository:

`https://github.com/Graphify-Labs/graphify`

Install:

```bash
uv tool install graphifyy
graphify install
```

Use:

```text
/graphify .
```

Use Graphify for:

- broad codebase discovery;
- dependency tracing;
- architecture questions;
- cross-file impact analysis.

Do not run full graph work for tiny local edits.

Add to `.claudeignore`:

```text
graph.json
graphify-out/
```

## 5. Superpowers

Repository:

`https://github.com/obra/superpowers`

Claude Code:

```text
/plugin install superpowers@claude-plugins-official
```

Use for:

- planning;
- TDD;
- systematic debugging;
- code review;
- multi-step/subagent workflows.

Do not use it for trivial changes.

## 6. wshobson/agents

Repository:

`https://github.com/wshobson/agents`

Add marketplace:

```text
/plugin marketplace add wshobson/agents
```

Recommended FloodGuard plugins:

```text
/plugin install machine-learning-ops
/plugin install data-engineering
/plugin install python-development
/plugin install unit-testing
/plugin install observability-monitoring
```

Install cloud/frontend plugins only when those phases begin.

## 7. K-Dense Scientific Skills

Repository:

`https://github.com/K-Dense-AI/scientific-agent-skills`

Install selected skills only.

Recommended:

```bash
gh skill install K-Dense-AI/scientific-agent-skills scikit-learn --agent claude-code
gh skill install K-Dense-AI/scientific-agent-skills statsmodels --agent claude-code
gh skill install K-Dense-AI/scientific-agent-skills geopandas --agent claude-code
gh skill install K-Dense-AI/scientific-agent-skills geomaster --agent claude-code
```

Optional:

```bash
gh skill install K-Dense-AI/scientific-agent-skills timesfm-forecasting --agent claude-code
```

Use TimesFM as a benchmark where appropriate, not automatically as the production model.

## 8. Anthropic Official Plugins

Use Claude's official plugin marketplace for:

- PR review;
- feature development/code review;
- security guidance;
- Claude setup automation.

Prefer official review tooling when available instead of creating many overlapping reviewer prompts.

## 9. Skill Selection Budget

Normal task:

- one primary domain skill;
- zero or one workflow skill;
- Graphify only when needed;
- Ponytail/Caveman as efficiency layers.

Complex production task:

- one domain skill;
- one workflow skill;
- one independent reviewer;
- Graphify if the task spans modules.

## 10. Model Selection for Agents

Prefer:

```yaml
model: opus
```

for:

- ML methodology;
- architecture;
- production-critical review;
- security;
- difficult debugging.

Prefer:

```yaml
model: inherit
```

for normal implementation where the current Claude model should be respected.

Avoid pinning an exact future model ID unless reproducibility requires it.
