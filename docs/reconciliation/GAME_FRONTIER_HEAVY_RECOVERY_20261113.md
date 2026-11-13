# Game Frontier heavyweight historical reconciliation — 2026-11-13

## Audited ancestry and source facts

Historical branch `feat/gf-n-jenkins-20261024` at
`dada3f1b4c05761492b44ac93c8b036fa7dc9a59` contained **377
historical ahead commits** and was **578 commits behind** exact
`main` `d5275f6cff2b660ec6b41455fedb51567b113ad5`.

GitHub's 207-path three-dot comparison reports 205 additions since the
*common ancestor*, **not** 205 source files absent from current main.
A complete Git-tree blob audit identified 202 Game Frontier source,
documentation and test paths suitable for direct comparisons. Of these:

- **195 exact blob matches** already exist in current main.
- **7 historical versions differed**, and newer main is deliberately kept:
  `docs/plan/GAME_FRONTIER_ADVANCED_PHYSICS_ASSURANCE_2026_10_19.md`,
  `frontend/app/frontier-navigation.tsx`,
  both mirrored `game_frontier_milestone_8.py` files,
  both mirrored `game_frontier_studio.py` files, and
  `tests/test_game_frontier_milestone_8.py`.
- 59 Jeeves Game Frontier canonical modules matched their corresponding
  AI-tree mirror blobs exactly; newer additions already on main include
  surveyed/cockpit controls, integrated 3D expedition authoring and
  authentic campaign audit-receipt validation.

The 7 changed files were deliberately restored from current main after
identifying that historical versions omitted cockpit UX, expedition
authoring, security-bound receipt validation or newer regression tests.
No archived implementation is permitted to regress those features.

## Separately audited, not overwritten

- `skeleton/ai/runtime/inference/local.py` is older in the historical
  branch. Retain the canonical modern local-first inference runtime.
- The historical Game Frontier native-smoke and validation workflow files
  are **different** from existing main workflow files. Retain modern
  security/runner/action/CI authority rather than replacing these.
- The historical root `TODO.md` differs from current main and is not a
  source-of-truth build artifact; retain current main.
- `BACKLOG.md` is byte-for-byte identical between the two heads.

Historical blob versions remain available through the source branch
first-parent ancestry; current main remains the second parent. No
history or original source commits were deleted, rewritten or force-pushed.

## Qualification and disposition

This historical branch is **reconciled for ancestry without source
regression**; all effective implementation and test files examined are
already on main, so the remaining candidate diff consists only of this
audit. Do not describe that as 202 newly delivered modules.

The available contemporary dedicated game/studio PRs still need their
own exact-head canonical mirror, 3D expedition, Godot export, cockpit,
local GGUF, device E2E, security, workflow-input, malware, artifact,
hygiene and backend qualifications. No merge/release claim follows from
historical commit ancestry alone.
