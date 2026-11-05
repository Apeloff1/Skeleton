# Transactional scene survival editor

`python -m skeleton scene-survival-author demo` previews the original
Lantern Hollow playable survival vertical with a portable replay bundle.

The editor accepts a canonical survival source, records a bounded edit
journal and seals source identity, revision and document digest. Every
edit requires the exact expected revision and source digest. Conflicting
or stale edits fail without modifying the original document.

Commands: `new --source-json JSON`,
`edit --document-json JSON --edit-json JSON --expected-digest SHA --expected-revision N`,
`verify --document-json JSON`,
`preview --document-json JSON --actions-json JSON`, and
`solve --document-json JSON [--max-states N --max-depth N]`.

Supported edits: `set_health`, `set_food_capacity`, `set_initial_food`,
`set_turn_limit` with a `value`; `set_hazard` or `remove_hazard`
with `scene_id` and `at` (plus `damage` for set);
`add_camp`/`remove_camp` with `scene_id` and `at`;
`add_food`/`remove_food` with `pickup`.
Edits are canonicalized and validated against actual tile topology.
No edit grants a gameplay item, and no editor can bypass replay.

The preview executes actual game actions and returns a portable source-
bound save; the solver returns a bounded replay-verifiable route witness.
`python -m pytest skeleton/testing/test_scene_tile_survival_author.py -q`
covers editing, optimistic concurrency, forged source rejection,
non-mutation on failure, preview, solver and installed CLI.
