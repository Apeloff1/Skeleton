#!/usr/bin/env bash
# Smoke test the cockpit: boot genesis, hit health, verify handles.
set -euo pipefail

python - <<'PY'
from skeleton.genesis import Genesis

g = Genesis(seed=42).boot()
health = g.health()

assert "kernel" in health["phases"]
assert "cortex" in health["phases"]
assert health["subsystems"] >= 20, f"expected 20+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress", "quad", "cortex"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, healthy={health['healthy']})")
PY
