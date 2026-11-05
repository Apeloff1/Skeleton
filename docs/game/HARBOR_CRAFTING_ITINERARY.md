# Lantern Quay playable waypoint itineraries

Compose deterministic navigation with actual gathering, crafting, trading,
delivery and choice transitions. Each stop has an authored `goal` coordinate
and one optional `action` (null means navigation only). The planner uses the
canonical NPC-aware bounded navigator and the canonical gameplay engine.

Example `stops.json`:

```json
[
  {"goal":[2,1],"action":{"op":"gather"}},
  {"goal":[2,1],"action":{"op":"gather"}},
  {"goal":[1,1],"action":null}
]
```

```sh
python -m scripts.game.harbor_crafting itinerary-build --bundle save.json --stops stops.json --expected-terminal-digest <verified-terminal-digest> > itinerary.json
python -m scripts.game.harbor_crafting itinerary-verify --itinerary itinerary.json
```

The portable artifact contains the original source-bound save, all actual
legal actions, per-stop replay custody, and the final verified checkpoint.
No movement, inventory, currency, quest, NPC collision, or choice rule is
overridden. Failed legs or interactions reject the whole itinerary, without
publishing a partial game save. At most 16 stops, 64 search ticks per leg and
8192 visited states per leg. Digests detect changes but are not signatures.
