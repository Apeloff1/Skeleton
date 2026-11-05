# Godot export + GF-D QA certification (`skeleton.godot_export`)

Pure-Python validators for Godot 4 projects plus thin, injectable runners around
the pinned engine (Godot 4.7.2, `GF-P0-134`). Static checks need no engine;
engine-backed checks go through `GodotRunner`, so tests substitute a fake process.

```bash
python -m skeleton.godot_export cases                         # case catalogue
python -m skeleton.godot_export certify path/to/project       # static only
python -m skeleton.godot_export certify proj --godot "$GODOT_BIN" --pin-sha256 <sha> \
    --export --out-dir out --format markdown                  # import, --check-only, export
python -m skeleton.godot_export provenance proj --artifact Linux=out/build/linux/game.x86_64 \
    --verdict SHIP --out manifest.json
python -m skeleton.godot_export verify manifest.json --base out --project proj
```

Exit code is 0 only when no Sev1/Sev2 case fails (SHIP).

| Prefix | Scope |
|---|---|
| GFD-00..06 | project parse, headless `--import`, log scan, `.godot/` cache, `--check-only`, `res://` references |
| GFX-01..09 | `export_presets.cfg`, platform options, `--export-release`, artifact format (ELF/PE/zip/wasm), `.pck` header, duplicate names, committed secrets |
| GFL-01..04 | offline GDScript lint: indentation, `extends`/`class_name` order, preload targets, duplicate `class_name` |
| GFP-01..04 | physics ticks, main scene, autoloads, 4.x feature tag |
| GFS-01..03 | static halves of GF-P0-38/74/96: RigidBody3D mass, pinned SoftBody3D, current Camera3D |
| GFB-01..02 | engine version / sha256 pin |

Provenance manifests (`skeleton.godot_export.provenance/v1`) are deterministic
JSON: artifact sha256 + size, an order-independent project tree digest that
ignores `.godot/`, `build/` and `export/`, git head, engine line and verdict.
`verify` re-hashes artifacts and fails on tamper, missing files, a changed
tree or a non-SHIP verdict.

Tests: `skeleton/testing/test_godot_export_*.py` with fixtures under
`skeleton/testing/fixtures/godot_export/`. `test_godot_export_native.py` runs
only when `GODOT_BIN` points at an executable engine and skips if it is not the
pinned version. Headless Godot uses the dummy renderer, so screenshots, shadow
casters and GPU timestep equivalence are not attested here (see
`scripts/run_game_frontier_gfd_native_checks.py`).
