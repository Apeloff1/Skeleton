# Bounded survival route proofs

`python -m skeleton scene-survival-route demo` searches real canonical
tile movement, pickups, locked exits, hazards, food and one-use shelters
for a playable original Lantern Hollow ending. The solver never invents
inventory or modifies the source. A found result includes a deterministic
action witness and a replay-verified portable save checksum.

Use `solve --source-json JSON [--target won|lost|draw]` or
`solve --session-json JSON` to continue from a verified checkpoint.
`verify --source-json JSON --plan-json JSON` independently repeats the
bounded search and the full gameplay replay. The same verify command
accepts `--session-json` for checkpoint-relative witnesses.

`max_states` is bounded by 4096 and `max_depth` by 64. Exhausted
searches return `inconclusive` with `budget_exhausted=true`, never
claiming a route is impossible. The state signature retains gameplay
resources, scene identity, position, pickups, health, food and used camps.
Shorter equivalent paths dominate longer ones. All output is inert JSON.

Focused acceptance:
`python -m pytest skeleton/testing/test_scene_tile_survival_route.py -q`.
Required exact-head CI and release gates remain separate.
