# Source-bound mission ending route solver

`python -m skeleton scene-mission-route --demo` searches for a shortest
legal action sequence to the authored `lantern_restored` ending. The solver
explores actual canonical scene actions, available authored dialogue options
and valid terminal mission decisions. It cannot grant reputation, teleport,
skip required pickups or fabricate a mission completion.

```sh
python -m skeleton scene-mission-route --demo
python -m skeleton scene-mission-route --source-json '<JSON>' --ending-id '<ID>'
python -m skeleton scene-mission-route --session-json '<JSON>' --ending-id '<ID>'
python -m pytest skeleton/testing/test_scene_mission_solver.py -q
```

The result carries source and initial state digests, the target ending,
exploration counts, bounded action witness and exact final state digest.
`verify_plan` replays a found route through the real mission runtime.
An exhausted state/depth budget returns `inconclusive`; a complete bounded
search without a witness returns `unreachable`. A terminal saved session
cannot be reinterpreted as reaching a different ending. This is offline
deterministic game logic, not an AI provider, native renderer or author
signature. Search caps: 4096 states and 128 actions.
