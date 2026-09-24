---
name: update-code-graph
description: Update/query Graphify when FloodGuard structural changes or broad dependency analysis require it.
---

# Update Code Graph

Use Graphify when:

- a task spans multiple modules;
- tracing dependencies;
- reviewing architecture;
- checking blast radius of a change;
- understanding an unfamiliar subsystem.

Do not use Graphify when:

- editing a tiny isolated file;
- changing documentation only;
- a direct file read is cheaper and sufficient.

Typical commands:

```bash
graphify update .
graphify query "<question>"
graphify explain "<concept>"
graphify path "<A>" "<B>"
```

Do not rebuild the full graph for a trivial local edit.

Ignore files (see `docs/15_CLAUDE_SKILLS_SETUP.md`):

- `.gitignore` is read by Graphify automatically (even outside a git repo);
- `.graphifyignore` adds Graphify-only excludes and can only exclude more;
- `.claudeignore` keeps generated graph files out of Claude prompt context.
