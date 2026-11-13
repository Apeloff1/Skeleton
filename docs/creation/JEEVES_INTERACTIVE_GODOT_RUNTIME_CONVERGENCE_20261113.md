# Jeeves native game-builder runtime: reviewed historical source convergence

**Stack parent:** GameForge/Galaxy/Frontier integration PR #5317 at
`a483b135b705bf3eef9ad2c160e2c74f3b0542e1`.

**Recovered implementation:** PR #5285 at
`06515a6e93f76d4fdf13067553438137dcdb2dac`.
The original branch is 369 commits ahead of the inspected historical main
and contains many unrelated application and CI changes. This integration
does **not** bring those 369 commits into main wholesale.

## Exact patch-first source proof

Seven original builder files were reconstructed by applying the #5285
file-specific GitHub PR hunks to the **current candidate** file bytes.
All seven reconstructed outputs matched the original #5285 blob byte-for-byte,
and each matched the corresponding `skeleton/ai/forge` source mirror:
- `skeleton/forge/game_design_spec.py`
- `skeleton/forge/game_builder.py`
- `skeleton/forge/game_content.py`
- `skeleton/forge/genre_project.py`
- `skeleton/forge/ai_builder/plan_schema.py`
- `skeleton/forge/ai_builder/plan_guard.py`
- `skeleton/forge/ai_builder/model_planner.py`

The eighth module `skeleton/forge/playable_runtime.py` is a
separate maintained original game runtime (44 KB of Python/GDScript),
transferred with its identical canonical AI mirror, not AI-generated
executable code. Two untouched historical regression suites are restored.
The 18 source/test paths are provenance-preserving exact blob transfers.

## Actual functional integration

- `build_playable_game` now attaches a distinct input-driven Godot scene
  through the existing `genre_project.attach_genre`. It does **not**
  claim that the old CoreLoop table proof is equivalent to a playthrough.
- Three maintained original genre gameplay loops: top-down arena shooting,
  2D platforming, and chamber/relic RPG, with ordinary player input,
  obstacles, combat/jump/loot, loss, win, pause and restart.
- Typed gameplay design fields for difficulty, palette theme, objective,
  player speed and encounter style; compiled parameters modify real
  encounter HP, damage, loot, platform gaps and in-game behavior.
- Local Jeeves planner may propose **bounded data only**. Strict JSON
  rejects duplicate fields, NaN/nonfinite input, oversized proposals,
  unknown code/path fields and violations of the user's explicit
  difficulty/objective/speed preferences.
- Pipeline outputs a separate `interactive` field and distinguishes
  native boot from an input journey. A headless boot is not proof of
  real human/device play.
- The pre-existing GameForge creator retains the 14 Galaxy matrices,
  158 selectable genre labels, ten-axis design cockpit, quest runtime,
  cross-device control profiles and eight other original Godot mini-games.
  The two separate build pipelines are not deceptively conflated.

## Focused verification on this exact candidate head

```sh
PYTHONPATH=.:backend python -m pytest -q \
  tests/test_forge_gameplay_design.py \
  tests/test_forge_interactive_runtime.py \
  skeleton/testing/test_historical_controls_full_catalog.py \
  skeleton/testing/test_multigenre_playable_slices.py \
  skeleton/testing/test_historical_gameforge_convergence.py
python -m compileall -q skeleton/forge skeleton/ai/forge
```

For pinned Godot native acceptance, explicitly set
`SKELETON_GAME_BUILDER_REQUIRE_GODOT=1` on a runner with Godot 4 installed;
a skipped native test does not qualify. Require exact-head Backend Quality,
Merge Readiness, App Foundation E2E, mirror/source parity, security,
artifact, malware, secret, dependency, license, Windows/WSL2 and local
Jeeves GGUF acceptance. No merge/auto-merge/release/installer approval.
