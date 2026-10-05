#!/usr/bin/env bash
# Verify the forge end-to-end: blueprint validation, JSON materialization,
# and the Godot emit → verify-until-green loop.
set -euo pipefail

python - <<'PY'
from skeleton.forge.universal import Forge

# 1. JSON target: build, validate, materialise
forge = Forge()
bp = forge.new_blueprint("verify-forge")
forge.instantiate(bp, "source", "input")
forge.instantiate(bp, "transform", "process")
forge.instantiate(bp, "sink", "output")
bp.connect(("input", "out"), ("process", "in"))
bp.connect(("process", "out"), ("output", "in"))

problems = bp.validate()
assert not problems, f"validation failed: {problems}"

result = forge.materialise(bp, era="extraction_now", target="json")
assert result["blueprint_id"] == bp.blueprint_id
assert len(result["execution_order"]) == 3
print("forge json target: OK")

# 2. Godot target: emit → static check → verify-until-green
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.gdscript_check import check_files
from skeleton.forge.verify_loop import forge_verify_until_green

files = emit_godot(compile_era("extraction_now"), title="verify-forge")
assert "project.godot" in files
problems = check_files(files)
assert not problems, f"static check failed: {problems[:5]}"

loop = forge_verify_until_green(files, request="verify-forge", max_rounds=2)
assert loop["accepted"], f"verify loop rejected: {loop['verification'].get('reason')}"
assert loop["trace"]["stopped_reason"] == "accepted"
print(f"forge godot target: OK ({len(files)} files, verify loop accepted)")

# 3. Materialise through the forge with repair loop enabled
result = forge.materialise(bp, era="extraction_now", target="godot", repair=True, max_rounds=2)
assert result["verification"]["accepted"]
print("forge materialise(godot, repair=True): OK")
PY
