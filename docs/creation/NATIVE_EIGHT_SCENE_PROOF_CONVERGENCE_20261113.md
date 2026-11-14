# Eight-scene real Godot qualification integration

**Source lineage:** main-target PR #5319,
`ca8cabf5847818239af24a3063b77a9bbfceb164`.
Historic prototype #5313 at
`30ed3ea8c4d973e12c2abae013ccee5205331115` contained an
independent scene playtester for three original Godot archetypes. The
current consolidated GameForge already ships **eight** deterministic
self-contained Godot mini-games and a source-bound launcher/autoload.
Copying the old three-mode launcher would downgrade that functionality.
Instead, this integration forward-ports the independent completion contract
to all **eight** existing maintained scenes.

## Functional integration

- Run the exact scene through an isolated, bounded Godot import + headless
  scene invocation, with a fixed 6,000-frame default and 180-second total
  deadline. Only an exit-zero scene with the correct original
  `ARCHETYPE_LOOP_COMPLETE <genre> <objective>` marker and no failure marker
  or script/runtime errors earns functional success.
- Strict source admission rejects unknown modes, incomplete file maps,
  invalid clocks and nonfinite or excessive time/frame budgets.
- Temporary Godot project storage is destroyed after every run, even if the
  external process reports errors; no network downloads or game-file
  destinations are admitted by the scene verifier.
- The engine's execution success and provenance are **separate**.
  `verified=true` is only set by the preexisting exact-binary artifact
  locator; process success with an env/PATH binary is reported as
  `passed=true`, `verified=false` and rendered as a warning, never green.
- Original main-world import and boot must have **zero exit code**; the
  previous imported-scene path permitted a nonzero import to reach the boot
  phase if the textual log had no recognized ERROR line.
- `GameForgeRun.execute(playtest="auto"|"require")` now records separate
  main-world and playable-sidecar results. `require` fails before
  writing the destination project if either check fails or Godot is
  unavailable; `auto` retains a truthful unqualified result.
- New explicit chooser in the full questionnaire defaults to off; Godot
  only. The review and run panels display both qualifications and the
  actual emitted Godot scene path.
- Existing eight original mini-game modes, 69 Galaxy offline genres,
  158 creator labels, 14 Galaxy matrices, 100+ sliders, ten-axis cockpit,
  B023/B024 input/script runtimes, Godot quest/launcher, local Jeeves
  diagnostics, resource/energy control and seven-stage conductor remain
  intact.
- The two changed Python implementation sources match their canonical AI
  mirrors byte-for-byte. No archive wholesale branch overwrite.

## Verification and explicit holds

Focused exact-head source tests (mocked Godot subprocess boundary):
```sh
PYTHONPATH=.:backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_eight_native_scene_qualification.py \
  skeleton/testing/test_gameforge_native_scene_convergence.py \
  backend/tests/test_native_eight_scene_api.py \
  skeleton/testing/test_multigenre_playable_slices.py
cd frontend && node --test scripts/skeleton-forge/native-scene-qualification.test.cjs
cd frontend && npm run typecheck
```

**Additional qualification not replaceable by mocks:** pinned Godot 4 binary
attestation, actual eight-game completion, installed Windows 11/WSL2 and
mobile/keyboard/gamepad UI journeys, live GGUF Jeeves and asset provenance.
All required final-head Merge Readiness, Backend Quality, App E2E, CodeQL,
workflow-input, secret/malware, artifact, dependency and hygiene gates must
also pass. Do not merge, auto-merge, release or certify first install while
these remain queued, failed, skipped, cancelled or unverified.
