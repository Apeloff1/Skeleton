#!/usr/bin/env bash
# Verify the forge end-to-end: boot genesis, build a blueprint, materialize it.
set -euo pipefail

python - <<'PY'
from skeleton.forge.universal import Forge

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
print("forge verification: OK")
PY
