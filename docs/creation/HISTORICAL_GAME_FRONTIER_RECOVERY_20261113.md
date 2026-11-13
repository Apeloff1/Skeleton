# Historical Game Frontier recovery — 2026-11-13

## Source identity

- Original preserved branch: `recovery/pre-rebase-game-frontier-20261113-r2`
- Source head: `df74a924dc4b7bcf639565737096b0e6adaeb70b`.
- Integration parent: `main` at `d5275f6cff2b660ec6b41455fedb51567b113ad5`.
- The source compare had 211 additive paths and two modifications to currently owned paths.
- Recovered here: **202 original additive blobs**, retaining their exact source blob identities.
- Jeeves source mirror: **59 byte-identical module pairs** under `skeleton/jeeves` and `skeleton/ai/agents/jeeves`.

## Components

Original candidate-only deterministic P0–P3 world model, virtual sensors (gyro, magnetic compass, sextant, altimeter), cinematic, locomotion, physics, ecosystems, wind, tides, camera/world coordinates, opt-in foreground GPS visual inspector, native Godot export proposals, quest sessions, source-backed replay journals, checkpoints, local vault, instrumentation, controller validation, authoring tools, and source test suites. Preserve original commits via the archive and recovery references.

## Deliberate exclusions

- `BACKLOG.md` and `skeleton/ai/runtime/inference/local.py`: historical modifications; current main stays authoritative, especially local-only inference.
- Two old Game Frontier workflows: replaced by a narrower new qualification workflow, without automatic release or merge.
- Four files already represented by the newer native runtime integration branch `reconcile/game-frontier-postmerge-native-runtime-20261113`; maintain as a separate review dependency to prevent overlapping ownership.
- Two historic transient status artifacts and `TODO.md`: do not overwrite current operational ledger.

## Qualification and release hold

The recovered code is source-complete for this selected archival comparison, **not** certified as a working production game or safe merge. Require exact-head Python compile, focused source tests, full backend and frontend checks, mirrored AI-tree/source-index, native Godot where applicable, security/CodeQL, artifact/malware/hygiene and first-install qualification. Never treat skipped or ancestor runs as passing. Independent device, Windows/WSL2 and reproducible Godot playtests remain unqualified.

## Integration with other recovered work

- GameForge questionnaire, sliders, 67 creator genres: PR #5296.
- 158 searchable genre-choice expansion (not 158 independently playable engines): PR #5300, stacked on #5296.
- Original quest runtime + constrained quest synthesis: PR #5304.
- Godot native quest bridge: `feature/quest-runtime-godot-integration-20261113-r01`.
- These branches have separate exact-head review requirements; preserve their work rather than conflicting or replacing code.

