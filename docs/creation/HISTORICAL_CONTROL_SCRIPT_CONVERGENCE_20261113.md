# B023/B024 runtime convergence with the current Galaxy/GameForge cockpit

Historical source: PR #5302 at dc8deadc6d03d96aacc9d0b60e741ac09a994a0a.
Independent integration parent: PR #5316 at
9b6150eafead819f8e3fda221516dd1ac61e8723.

This tree preserves all 16 original authored B023/B024 source/test/document
blobs. The one shared backend route is reconciled additively, without
overwriting the 14 Galaxy matrices, 100+ authoring parameters, the ten-axis
cockpit, 158 genre search, eight Godot games, quest runtime or source receipts.

- B023 restores bounded capability-scoped sandboxed scripts, reload quotas,
  diagnostics and canonical source mirrors.
- B024 restores remappable keyboard/gamepad/touch actions for all 67 original
  Galaxy genres and existing questionnaire labels.
- All 158 modern genre labels now expose bounded *semantic input layouts*
  using category fallback for additional names, with explicit historical
  mapping precedence. 158 labels does not mean 158 playable native engines.
- The existing offline game campaign bridge remains the only authority for
  movement, collision, inventory, save/restore and replay verification.
  Unsupported analog/racing input is not silently translated into grid moves.
- A new selected-genre, opt-in, read-only inspector shows mapped controls in
  the guided creator without raw device capture or code execution.
- API GET /api/skeleton/controls/genres and
  GET /api/skeleton/controls/genres/{genre} expose versioned input descriptors.

Focused qualification (after commit):
```sh
PYTHONPATH=.:backend python -m pytest -q \
  backend/tests/test_gameforge_control_profiles.py \
  skeleton/game/presentation/test_genre_action_profiles.py \
  skeleton/game/presentation/test_input_actions.py \
  skeleton/ecs/test_script_runtime.py \
  skeleton/ai/runtime/ecs/test_script_runtime.py \
  skeleton/testing/test_genre_playable_adapter.py \
  skeleton/testing/test_historical_controls_full_catalog.py \
  skeleton/testing/test_historical_gameforge_convergence.py
cd frontend && node --test scripts/skeleton-forge/{controls-preview,historical-convergence,multigenre-playable}.test.cjs
cd frontend && yarn typecheck
```

Full exact-head Merge Readiness, Backend Quality, App Foundation E2E,
security, source mirror, CodeQL, dependency, malware, artifact, native
Godot/device, Windows and first-install evidence must pass before merging.
No release or first-install certification is implied.
