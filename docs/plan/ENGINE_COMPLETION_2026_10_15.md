# October 15 engine completion: shared session bindings

This change closes **seven integration gaps**, not seven newly authored game
simulations. Source implementations were already located in
`skeleton/ai/game_builder/advanced_*_runtime.py` and have existing domain
regression suites. Previously their editors were categorized `authoring_only`
despite operational `start`, `step`, `default_layout`, `normalize_layout`
and `apply_scene` functions.

New canonical bindings: `procedural_world`, `voxel`, `parkour`,
`ecosystem`, `sports`, `npc_society`, `dialogue`.

The shared `run_advanced_session` now executes these through its existing
bounded input, deterministic transcript, action allowlist, event receipts,
content-digest chain, and `verify_advanced_session` verification. The
authored-scene path also invokes each existing exact-schema layout validator
and source-to-state application, maintaining seed and configuration binding.
There is no new service, runtime provider, engine root or authority boundary.

### Unbuilt/unwired frontier after this change

The 43 editor catalog still contains `authoring_only` entries for:
`economy`, `narrative`, `cinematics`, `audio`, `animation`,
`ui_hud`, `accessibility`, `localization`, `networking`,
`save_system`, `platform_profile`. These require executable owner-specific
integration rather than a premature maturity flag.

### Verification and limitations

Relevant current domain suites: `tests/test_game_builder_advanced_procedural_world.py`,
`tests/test_game_builder_advanced_voxel.py`,
`tests/test_game_builder_advanced_parkour.py`,
`tests/test_game_builder_advanced_ecosystem.py`,
`tests/test_game_builder_advanced_sports.py`,
`tests/test_game_builder_advanced_npc_society.py`,
`tests/test_game_builder_advanced_dialogue.py` and
`tests/test_game_builder_advanced_engine_bindings.py`.

These are **offline reference game runtimes**. They do not establish physical
rendering, native hardware certification, independent release verification,
or completion of the entire product.
