# GameForge quest bridge — recovered application integration

This entrypoint joins the seven-stage archived GameForge conductor with the
B028/B030/B037 quest composition and objective runtime. The conductor owns
region topology, era binding, placeholder-artifact bytes and stage receipts.
The quest runtime owns the objective DAG, earned rewards and its replay
snapshot. The bridge does not replace either implementation.

## Entry points

- `python -m skeleton gameforge-quest`
- `python -m skeleton.app.gameforge_quest_cli`
- Installed console script: `skeleton-gameforge-quest`

Commands consume a single JSON document from standard input and emit one
bounded canonical JSON document to standard output. They open no file or
network connection. Exit 1 rejects a source, action sequence or receipt; exit
2 is a malformed CLI invocation.

Use a request such as:

```json
{
  "schema": "skeleton.gameforge.quest_bridge.request.v1",
  "vision": {
    "title": "Lantern Harbor",
    "pitch": "Explore a coastal town and restore lost lights",
    "genre": "adventure",
    "era": "HOUSE_ERA",
    "pillars": ["exploration", "story"],
    "target_minutes": 12
  },
  "config": {"budget_bytes": 200000, "regions": 8, "target": "bundle"},
  "quest": {
    "packs": [
      {"id": "movement", "provides": ["movement"]},
      {"id": "quest", "provides": ["quests"], "requires": ["movement"]}
    ],
    "pack_ids": ["quest", "movement"],
    "policy": {
      "allowed_reward_kinds": ["gold"],
      "max_reward_per_step": 3,
      "max_total_reward": 48
    },
    "seed": 31,
    "quest_length": 8,
    "npcs": {"ranger": "r00", "keeper": "r03"}
  }
}
```

## Design and gameplay workflow

| Command | Input |
| --- | --- |
| build | Original request |
| verify | Object containing independent request and design receipt |
| play | Object containing request and actions |
| verify-play | Object containing independent request and session receipt |
| resume | Object containing request, previous session receipt, additional actions |

The build operation runs all seven conductor stages, verifies its manifest
against the actual in-memory placeholder bytes, derives a quest from its
world, and produces a route witness which is executed against the objective
engine. Region edges are made bidirectional specifically because the existing
WorldPlan validator treats its edges as an undirected graph. The bridge rejects
dangling or disconnected generated graph data and unknown NPC placements.

The player session starts empty. A design witness is a demonstration, not an
award of progress. Only explicit actions affect session state:

- {"type":"move","to":"r01"} is accepted only for a neighbor of the current region.
- {"type":"resolve","objective":"s0","npc":null} requires the correct location,
  active objective and exact NPC identity (null only if the quest requires no NPC).

The current receipt exposes legal actions, earned rewards, location, status and
the canonical objective snapshot. Duplicate resolution, locked objectives,
teleportation, incorrect NPC identity, and actions after completion fail closed.
Resume independently rebuilds the original design, replays the old ledger,
compares every canonical byte, and only then applies the additional actions.
No authority is conferred by a submitted digest or saved status.

The command is bounded to 64 regions, 128 objective steps, 8192 player actions,
2 MiB of JSON, and a bounded in-memory artifact set. Conductor budget refers to
its existing estimated asset plan; actual placeholder bytes are separately
counted and capped. This prototype does not claim those bytes are usable art.
The SHA-256 identities are deterministic integrity checks, not authentication
or signatures. Independent source custody is required.

## Example using shell redirection

```sh
python -m skeleton gameforge-quest build < request.json > design.json
python -c "import json;print(json.dumps({'request':json.load(open('request.json')),'actions':[]}))" | python -m skeleton gameforge-quest play > initial.json
python -c "import json;print(json.dumps({'request':json.load(open('request.json')),'receipt':json.load(open('initial.json')),'additional':json.load(open('design.json'))['route_witness']}))" | python -m skeleton gameforge-quest resume > completed.json
python -c "import json;print(json.dumps({'request':json.load(open('request.json')),'receipt':json.load(open('completed.json'))}))" | python -m skeleton gameforge-quest verify-play
```

## Qualification

Run these against the final PR head:

```sh
python -m pytest -q skeleton/testing/test_gameforge_quest_bridge.py skeleton/testing/test_original_quest_cli.py skeleton/testing/test_original_quest_slice.py skeleton/testing/test_quest_objective_runtime.py skeleton/testing/test_genre_template_composition.py skeleton/testing/test_constraint_quest_synthesis.py skeleton/gameforge/test_gameforge_conductor.py
python -m compileall -q skeleton/app/gameforge_quest_bridge.py skeleton/app/gameforge_quest_cli.py skeleton/app/original_quest_cli.py
python -m skeleton capabilities --main-cli-audit
```

Then build and install a clean wheel, run its installed commands, and verify all
mandatory exact-head CI and security checks. The browser/backend, native Godot,
device, Windows/WSL2, GGUF, Docker and release-provenance boundaries remain
separate. The bridge is abstract region navigation and objective replay, not
native rendered gameplay. No merge or release authorization.
