# Godot export / GF-D QA fixtures

Tiny, original Godot 4 projects used by `skeleton/testing/test_godot_export_*.py`.

* `good/` - certifies SHIP statically: parseable settings, current Camera3D,
  RigidBody3D with positive mass, pinned SoftBody3D, clean GDScript, valid
  Linux and Web presets.
* `broken/` - deliberately defective; every defect maps to one case id
  (see `EXPECTED_FAILURES` in `test_godot_export_gfd_qa.py`).

No binaries are committed; engine-backed tests copy `good/` to a temp dir and
run only when `GODOT_BIN` points at the pinned Godot 4.7.2 build.
