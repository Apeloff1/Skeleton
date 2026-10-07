# Jeeves app tree

Law: one implementation, many faces. Source of truth stays in `complete/`.

```
apps/jeeves/
  src/
    index.js agent.js ai.js context.js conductor.js
    control.js idle.js ui.js
  bins/jeeves.js
  planes/ working episodic semantic procedural attention artifacts
```

Batch 1: facades + planes (merged).
Batch 2: control hub, idle controller, UI command plane.
Batch 3 later: KEEP/SHIM/FOLD inventory of leftover root sprawl.
