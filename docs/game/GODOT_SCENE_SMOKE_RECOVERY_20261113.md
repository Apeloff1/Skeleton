# Godot bounded scene smoke — historical API reconciliation

The older Studio B source had a bounded `GodotRunner.play_scene` primitive,
but the current Godot runner no longer exposed it. This integration carries
forward that method **without replacing** the current runner's hardened
`export_verified` descriptor and artifact-custody checks.

### Restored implementation
- Validates canonical `res://` paths: a nonempty `.tscn` resource, no dot
  components, backslash, control bytes, or path segments escaping the project.
- Bounds scene frame count to integers 1–36,000 and timeout to 1–3,600 seconds.
- Uses the native Godot `--quit-after` engine boundary with the canonical
  existing `GodotRunner.run` process handling. A successful exit is only
  a smoke result, **not** proof of gameplay completion or release readiness.
- Preserves the newer mainline fail-closed export path and current binary
  custody API. Does not reintroduce historical `export_with_evidence`,
  which was superseded by `export_and_inspect`.

### Coverage
- Source-preserved `tests/test_godot_scene_smoke_v6.py` rejects malformed
  paths, frame/time budget violations, and process failure.
- Source-preserved certification regression proves an empty native report
  cannot certify a release.
- Adapted `tests/test_godot_export_artifact_custody.py` exercises the
  current API's binary digest, PE header, missing/empty output, symlink and
  overwrite failure, and retry behavior; synthetic headers are **fixtures**,
  not evidence of real native export.

This branch preserves historical ancestry and merges against current main.
It remains draft review-only until exact-head focused pytest and full
security/CI checks pass. Independent device, executable, Godot import and
release-provenance evidence remains required.
