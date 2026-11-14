# Archived game creation B028 + B030 + B037 recovery

This is source-preserving revival of three original #807 game-builder layers:

- `archive/pre-rebase-807-b028-20261113-130d7927`:
  `quest_objective_runtime.py` — deterministic quest objectives, dependencies,
  fail states, rewards, replay and sealed snapshots.
- `archive/pre-rebase-807-b030-20261113-5b072c04`:
  `genre_template_composition.py` — source-bound immutable mechanic packs,
  capability requirements, conflict checking and reproducible slice manifests.
- `archive/pre-rebase-807-b037-20261113-ff9b6c2b`:
  `constraint_quest_synthesis.py` — seeded, world-reachable quest generation
  with NPC, prerequisite, reward and content-policy gates.

## Actual integration

`original_quest_slice.compose_verified_quest_slice` connects the three
modules: canonical pack registration → conflict-checked mechanic composition
→ world-bound generation → runtime-typed objective contract → abstract
playthrough with earned rewards → exact-source digest.

The path is deterministic, offline and does not require remote AI or run
generated code. Original and newly added regression suites are retained.

The archive B037 generator previously accepted excessive step and retry
counts and invalid reward budgets; the version here bounds step count,
attempts, world size and reward policies before any synthesis begins.

## Status and limits

This is a callable builder-domain module integrated with the existing
`skeleton.ai.game_builder` subsystem, not a replacement for its newer
Director or a claim of a native Godot playable game. Native engine porting
and project save/output adapters need additional qualification.

Test after branch implementation:
`python -m pytest -q skeleton/testing/test_quest_objective_runtime.py skeleton/testing/test_genre_template_composition.py skeleton/testing/test_constraint_quest_synthesis.py skeleton/testing/test_original_quest_slice.py`
Then exact-head Backend Quality, Merge Readiness, security, source
provenance, gameplay replay and native/device gates before merging.
