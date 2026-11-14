# Feature-branch conservation wave: Frontier, Godot, energy and scene custody

Source-preserving continuation of the 158-genre GameForge and B023/B024
convergence. Parent candidate is PR #5317 at
`914d8da1516b2698074fcc8227026baa2a3cad0d`.

## Imported exact-source slices

| PR | Historical source head | Integrated paths | Functional significance |
| --- | --- | ---: | --- |
| #5298 | `c773d734c11327a06ae07670c41ca0de9eebda6f` | 2 | 2,500-node scene-graph, replay/cold-restore, malformed JSON and bounded scene bytes |
| #5301 | `6dcb0b08cd5a4b5572c5638ca3dc097b358c0118` | 5 | Guarded native Godot `play_scene` smoke, export artifact custody and empty certification rejection |
| #5297 | `e02484c1bfd0afbf849ad3ec152c9e9bf16d5156` | 5 | Measured offline power hysteresis, worker anti-thrash, stale observation refusal and CLI flags |
| #5288 | `f3aef794a1575915df2b938547fa49b0ec16a792` | 6 | Deterministic Frontier physics/weather/presentation-tier contract, LOD and native tests |

All eighteen source paths were moved using their Git blob IDs, preserving
the reconciled 2026 source bytes. The updated Godot runner, energy CLI and
desktop source qualifier each come from source PRs based on the same
`d5275f6...` main commit, with no overlapping modifications in the
consolidated GameForge parent.

**Explicit exclusion:** #5288 also changes a digest in
`machine/product_surface_specification.json` for an unrelated Discourse
source file. The current GameForge metadata from #5316 is retained rather
than overwriting it with stale metadata.

## Exact-head validation after final commit

```sh
PYTHONPATH=.:backend python -m pytest -q \
  tests/test_scene_graph_deep_validation.py \
  skeleton/testing/test_scene_bytes.py \
  tests/test_godot_export_artifact_custody.py \
  tests/test_godot_export_empty_certification.py \
  tests/test_godot_scene_smoke_v6.py \
  skeleton/testing/test_offline_energy_hysteresis.py \
  tests/game_frontier_native/test_native_runtime_4167.py
PYTHONPATH=.:backend python -m pytest -q \
  backend/tests/test_gameforge_control_profiles.py \
  skeleton/testing/test_historical_controls_full_catalog.py \
  skeleton/testing/test_genre_playable_adapter.py
cd frontend && node --test scripts/skeleton-forge/controls-preview.test.cjs
```

These source tests do not assert physical device, complete native-game
playthrough, installer, local GGUF, system-wide release or full first-install
qualification. Exact-current-head CI/security/Godot/Windows evidence and
approval remain mandatory; skipped, queued, cancelled or ancestral runs
cannot be counted as passes. No immediate main merge or release.
