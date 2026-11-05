# Interactive source-bound tile survival

`python -m skeleton scene-survival-play demo` launches the original
Lantern Hollow survival game. Enter `north`, `south`, `east`,
`west`, `collect PICKUP`, `travel EXIT` or `rest`.
A strict JSON action is also accepted. The prompt shows current health,
food, position and the actions actually legal in the canonical engine.

`play --source-json JSON` starts a new game; `resume --session-json JSON`
continues a replay-verified save. Optionally require
`--expected-source-digest SHA` and choose
`--checkpoint-every 1..64` or `--max-turns 1..256`.

Each line is an inert bounded action; three invalid attempts cause a
verified checkpoint and nonzero exit. EOF, no legal action and interactive
turn-budget exhaustion also emit verified restartable checkpoints. Every
accepted action includes a receipt. Terminal results include a complete
portable bundle checked by source digest, event journal and replay.

For automated acceptance run
`python -m pytest skeleton/testing/test_scene_tile_survival_interactive.py -q`.
Exact-head CI and consumer qualification are still mandatory.
