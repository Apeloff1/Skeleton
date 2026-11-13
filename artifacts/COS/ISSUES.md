# Mined issue specs (2026-10-24, all OPEN). Owners per 5h plan.

## #4167 [Game Frontier P0] native runtime integration (Santo, L)
State: reference source on `feature/game-frontier-p0-p3-20261019`; 74 focused tests passed at `e5cd4fe9` (run 39188618020). Candidate-side only.
Remaining: architecture/construction/provider checks; wire weather/clouds/rigged meshes into canonical render/physics; Godot export + animated collision test with screenshots; UI + save/restore; prove 30/50/60/120 present rates without changing physics ticks; chunk verifier in real streaming path; RPG authoring UI in Studio.
Acceptance: boxes ticked with evidence (tests, screenshots, run IDs). Deps: none; blocks #4168–#4170. Unknown: whether the feature branch is merged into main.

## #4168 [P1] world model / 3D reconstruction / checkpoint adapters (Bork, this push: stubs + licence matrix)
All boxes open. Needs legally usable checkpoints (licence/money: ask first). Deps: #4167.

## #4169 [P2] closed-loop cognition, WHAM, world-axis (Olly, this push: loop scaffold + win/loss tests)
All boxes open. Deps: #4167.

## #4170 [P3] production qualification (Gronk, this push: FPS telemetry harness + checklist)
All boxes open; no qualification claimed. Deps: #4167–#4169.

## #4138 unbound domain `dragon-conversation-micro-projection` (Klint, plan only)
Parked by #4135. Options: bind (topology + code + tests, spine count 26→27), retire (delete: needs approval), keep parked with status `planned`. Gate: `tests/test_traceability_spine.py`, `scripts/generate_master_traceability.py --check`.

## #4133 8 boot route modules skipped (Glenny, + Murash for creator_economy/marketplace)
creator_economy/marketplace: `emergentintegrations.payments` missing. git_operations: `/app` mkdir at import. jeeves_media: +imageio. lafs: +scipy. sorting_vault: `SortingRule.target` default vs `min_length=1`. swarm_*: lazy Mongo. `routes_registry.py:71`: log exception type + message. Acceptance: 0 `SKIPPED import_failed`, one regression test per module.

## #4122 persistence consolidation (Coder Lead)
Now: deprecation docstrings in persist/storage/state + `skeleton/ai/runtime` mirrors, plus a guard test. No behaviour change or removals. Later: move impls and add shims after the arch contracts land; retiring shims is a delete and needs approval.

## #3721 repo atlas + duplicate inventory (Wally, L)
Pinned-SHA tree inventory, indexes, exact and near-duplicate reports, no automatic dedup deletion, large artifacts outside Git. Reuse `skeleton/repo_intelligence/git_index.py`.

## #807 100-batch program (lane owners in BOT_BRIEF.md)
B001/B003 merged, B002 on main, B006 partial; the held branches for B004/B005/B007/B009/B011/B012 are not on the remote.

## #80 FRONTIER consolidation (Carrol, docs)
Open tail: #540 security umbrella; #127 needs a green current-main Merge Readiness run plus admin enforcement (a permission change: ask first).
