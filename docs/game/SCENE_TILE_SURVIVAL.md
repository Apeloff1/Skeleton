# Source-bound scene tile survival

`python -m skeleton scene-survival demo` runs the original Lantern Hollow
survival route. This is a real gameplay layer on canonical `scene-tiles`:
collision, item pickup, key-gated travel and endings remain delegated to the
existing engine. Survival adds authored damage tiles, one-use shelter,
earned food, health and a bounded action budget.

## Authoring

A source object has `schema_version: skeleton.scene_tile_survival.v1`,
`tile_source` (a complete canonical tile source), `max_health`,
`max_food`, `initial_food`, `turn_limit`, `hazards`, `camps`, and
`food_pickups`. Each hazard has `scene_id`, `at: [x,y]` and `damage`.
Each camp has `scene_id` and `at`. Food pickups are canonical
`scene_id:pickup_id` references; they cannot mint unearned items.
Hazards and camps must be walkable, reachable and non-overlapping.
No authored code is evaluated. Unknown keys and invalid JSON fail closed.

## Playing

Actions are `{"kind":"tile","action":{"kind":"move","direction":"east"}}`,
`{"kind":"tile","action":{"kind":"collect","pickup_id":"find_key"}}`,
`{"kind":"tile","action":{"kind":"travel","exit_id":"north"}}` and
`{"kind":"rest"}`. Rest is only allowed at an unused authored camp
with earned food and missing health. Entering a hazard damages health.
Zero health loses the game; canonical endings otherwise determine victory
or loss. Exhausting the turn budget results in a draw.

Use `simulate --source-json JSON --actions-json JSON`,
`resume --session-json JSON --actions-json JSON`,
`verify --session-json JSON`, `export --session-json JSON`,
or `import --bundle-json JSON`. Saves include canonical nested tile
checkpoints, a parent-linked save lineage, event receipts and digests.
All replays reconstruct state from source and actions. Portable bundles
validate checksum, source digest, state digest and the entire journal.

## Acceptance

`python -m pytest skeleton/testing/test_scene_tile_survival.py -q`
covers original victory, split checkpoint replay, collision and hazard
effects, earned food, shelter exhaustion, terminal loss, malformed source,
tampered saves, forged receipts, bundle integrity and CLI round trips.
Release qualification still requires the exact-head repository gates.
