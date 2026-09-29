# Jeeves app tree

Law: one implementation, many faces. Source of truth stays in `complete/`.
`apps/jeeves` is the operator map. Do not fork copies.

```
apps/jeeves/
  TREE.md                 this file
  README.md
  src/
    index.js              public barrel
    agent.js              → complete/cbm26-agent
    ai.js                 → complete/cbm26-ai
    context.js            → complete/cbm26-ai/context
    conductor.js          → complete/master-omega
  bins/
    jeeves.js             CLI
  planes/
    working/              RAM — working memory, budget
    episodic/             store / jsonl (gitignored payloads)
    semantic/             consolidated segments
    procedural/           skills
    attention/            9-cube hook
    artifacts/            pointers only — no Godot blobs
```

## Planes

| Plane | Lives | Not |
|-------|-------|-----|
| working | RAM, evicted | disk |
| episodic | store append | context window |
| semantic | consolidated segments | raw chat |
| procedural | skill registry | prompts as code |
| attention | cube lattice | token dump |
| artifacts | pointers / LFS | 100MB binaries in git |

## Workload batches
1. Facades + TREE (this PR)
2. Move CLI entry to `apps/jeeves/bins`
3. Plane folders + .gitkeep
4. Do not copy `complete/` into `apps/` — re-export only
