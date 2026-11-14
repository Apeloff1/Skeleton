# Game Frontier archival reconciliation — 2026-11-13

## Verified state (corrected against final main trees)

- Archived source: `recovery/pre-rebase-game-frontier-20261113-r2` at `df74a924dc4b7bcf639565737096b0e6adaeb70b`.
- Main source: `d5275f6cff2b660ec6b41455fedb51567b113ad5`.
- **202 candidate archive files checked against current main tree; 195 had identical Git blobs and 7 differed.**
- The initial commit's seven older versions are **restored to current main** in the subsequent repair commit; **no historical implementations overwrite the newer main implementations**.
- Mirror comparison: 59 archival Jeeves module pairs were byte-identical.
- The 211 `added` classifications from comparison of divergent ancestry do *not* mean those paths were absent in current main. Direct final-tree comparison is authoritative.

## Already present on main

Game Frontier physics, P0–P3 world-model logic, instruments (gyroscope, compass, sextant, altimeter), Godot/RPG authoring proposals, offline deterministic simulation, quest session replay and vault, virtual navigation and the foreground GPS opt-in inspector were already present in main at this source snapshot.

## Still open as independent integration work

- #5296: historical GameForge guided questionnaire, cockpit controls and 67 specialty genres.
- #5300: 158 selectable genre/subgenre labels, not 158 certified playable genre engines.
- #5304: constrained quest runtime and synthesis.
- `feature/quest-runtime-godot-integration-20261113-r01`: native quest bridge.
- `reconcile/game-frontier-postmerge-native-runtime-20261113`: separate P0 native runtime path.
- Need product-level wiring and exact-head end-to-end verification rather than falsely counting historical blobs as newly recovered.

## Qualification rules

This correction is review-only. No merge, auto-merge or launch until exact-head source mirror, backend/frontend, TypeScript, native engine, source-index, security, artifacts/hygiene and device/first-install checks qualify. A skipped job never counts as a pass.
