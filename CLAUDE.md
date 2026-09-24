# FloodGuard Penang — Claude Code Entry Point

@AGENTS.md

## Working Style

- Treat this as a production ML engineering repository.
- Read only the smallest relevant context required for the task.
- Check `.claude/rules/skill-routing.md` before selecting skills or subagents.
- Use task-specific skills instead of loading every installed skill.
- Keep changes scoped to the requested task.
- Do not perform unrelated refactors.
- Prefer existing project abstractions before adding new ones.
- Verify behavior before declaring completion.

## Non-Negotiable ML Rules

- Never fabricate datasets, flood events, APIs, model results, benchmarks, or achieved metrics.
- Never introduce future-data leakage.
- Do not randomly split temporal flood data when it would leak future information.
- Fit scalers, imputers, encoders, and other learned preprocessing only on training data.
- Keep targets separate from measured results.
- Prioritize flood-event recall and false-negative analysis, not accuracy alone.
- Do not introduce deep learning simply to make the portfolio look more advanced.

## Skill Use

Routing priority:

1. project correctness and safety rules;
2. task-specific domain skill;
3. workflow methodology when complexity justifies it;
4. Graphify for broad codebase context;
5. Ponytail for minimal implementation;
6. Caveman for concise output.

### Token / Context Efficiency

- **Graphify**: use for cross-module dependency or architecture questions instead of repeatedly reading the whole repository.
- **Ponytail**: use after understanding the task to avoid over-engineering and unnecessary code.
- **Caveman**: use to compress prose/tool-output overhead, preferably `lite`.
- Never compress away exact code, commands, paths, metrics, warnings, errors, or data-quality/security findings.

## Superpowers

Use Superpowers for:

- multi-step implementation plans;
- meaningful TDD cycles;
- systematic debugging;
- complex code review;
- subagent-driven development.

Do not invoke heavyweight workflow machinery for tiny edits.

## Completion

After implementation:

1. run targeted tests;
2. run relevant broader tests;
3. run Ruff;
4. run relevant mypy/type checks;
5. verify temporal/data-quality implications;
6. verify documentation if behavior changed;
7. report measured outcomes only.
