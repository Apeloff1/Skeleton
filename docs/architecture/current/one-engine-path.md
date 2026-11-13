# One engine path: `build_playable_game`

TD ruling: there is exactly **one** playable-game executor,
`skeleton.forge.game_builder.build_playable_game`. Everything else is an adapter:

- CLI `skeleton game` and `skeleton dev game build`
- `POST /api/v1/game/build`
- `POST /api/v1/gameforge/run` (`skeleton/api/routes.py`, a thin adapter that imports
  `build_playable_game` and `project_operator_http`)
- `skeleton/forge/game_build_queue.py`, `skeleton/developer/game_cli.py` and the swarm studio
  agents call it directly.

**Open question:** Projects builds (`POST /api/v1/projects/{id}/builds`) create a `game.build`
job through `skeleton.app_services`. On main at `9a73a0cb`, no module under
`skeleton/app_services` imports `build_playable_game`, so this page doesn't claim that job
reaches the executor.

Materialisation stays inside `GameForgeRun.execute` (`Forge.materialise` / `godot_emit`); adapters
must not materialise on their own.

## Contract of the executor

- `brief` is a string or a `skeleton.projects.v1` object; `coerce_brief` rejects any other
  `schema_version`.
- `deadline_s` (default `DEFAULT_DEADLINE_S` = 120 s) is **one** budget across materialisation,
  content, every prove round, the QA repair pass, project write and both hooks. A stage is not
  entered once the deadline has passed.
- `planner` / `qa` hooks (`PlannerHook`, `QaHook`) default to no-ops. A planner proposal that
  changes genre, engine, brief or scope is discarded. A QA `repair_requested` runs at most one
  more `prove_and_repair` pass.
- The return value is `skeleton.game_builder_run.v1`; `_operator` (the ten-stage legacy report)
  is stripped by `public_payload`.

The `skeleton/ai/forge/game_builder.py` copy is a byte twin, not a second engine.

## References

- `skeleton.forge.game_builder:build_playable_game`
- `skeleton.forge.game_builder:coerce_brief`
- `skeleton.forge.game_builder:prove_and_repair`
- `skeleton.forge.game_builder:PlannerHook`
- `skeleton.forge.game_builder:QaHook`
- `skeleton.forge.game_builder:PROJECTS_SCHEMA`
- `skeleton.forge.game_builder:DEFAULT_DEADLINE_S`
- `skeleton.forge.game_builder:project_operator_http`
