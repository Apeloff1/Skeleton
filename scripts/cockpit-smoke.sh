#!/usr/bin/env bash
# Smoke test the cockpit: full stack — 11 phases, federation, Context
# Fabric, Support System, and the over-achiever OverseerEngineV35
# (V3 paramount + energy + self-healing recovery + fleet gov + atlas).
set -euo pipefail

SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

python - "$SMOKE_DIR" <<'PY'
import sys, time
from skeleton.genesis import Genesis

smoke_dir = sys.argv[1]

g = Genesis(seed=42).boot()
health = g.health()

assert "support" in health["phases"], f"support phase missing: {health['phases']}"
assert health["subsystems"] >= 46, f"expected 46+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election", "fleet",
            "fabric", "workorders", "backlog", "planning", "queue", "oracle", "syntax_fixer", "cycle",
            "support", "loader", "agentic_rag", "overseer", "engine", "engine_v2", "engine_v3", "engine_v35"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# Engine V3.5: over-achiever telemetry at boot, fleet attached
v35 = g.get("engine_v35")
assert v35._ticks >= 1, "engine v35 never ticked"
assert v35.fleet is not None, "fleet governor not attached"
tick = v35.tick()
d = tick.to_dict()
for key in ("control", "v3", "energy", "recovery", "fleet", "atlas"):
    assert key in d, f"tick missing {key}"
assert 0.05 <= d["control"] <= 1.0
assert d["fleet"]["attached"] is True
assert d["energy"]["draw"]["total_w"] > 0.0

# V3.5 budget is authoritative on the loader
loader = g.get("loader")
v35_cap = v35.v3.base_budget.scaled(d["control"]).max_resident_planes
assert loader.max_resident == v35_cap, f"loader cap {loader.max_resident} != v3.5 budget {v35_cap}"

# Capability atlas: honest answer, critical always available
atlas_summary = d["atlas"]
assert atlas_summary["total"] >= 15
assert "governor.throttle" in atlas_summary["available"]
narration = v35.narrate_capabilities()
assert narration.startswith("On this device")

# Recovery engine wired and cycling
recovery = v35.recovery
assert isinstance(recovery.stats()["faults"], int)

# Fleet governance cycle produces a device report
status = v35.status()
assert status["fleet"]["registry"]["devices"] >= 1

# Support cycle + Agentic RAG
fabric = g.get("fabric")
fabric.distill("push files to github. search the web for docs. build pdf.", 1500)
support = g.get("support")
out = support.support_cycle(fabric)
assert len(out["loaded"]) >= 1
g.get("quad").ingest_document("smoke-rag", "The Forge produces blueprints. Skeleton is a game engine.")
rag = g.get("agentic_rag")
result = rag.retrieve("how does the forge relate to blueprints?")
assert result.query_class == "relational" and result.coverage > 0

# ResponseCycle conversation loop
from skeleton.api.server import ServerState
state = ServerState()
state.wire_from_genesis(g)
session = state.jeeves.open_session("smoke-user")
r1 = state.jeeves.ask(session.session_id, "push these files to github")
assert "cycle" in r1 and r1["cycle"]["orders_executed"] >= 1
r2 = state.jeeves.ask(session.session_id, "what next?")
assert "interjection" in r2

# Fabric: 18 systems, golden path, syntax repair, backlog chain
queue = g.get("queue")
assert len(queue.score({"priority": 5.0})) == 18
fabric.planning.decompose("finish product", [
    {"description": "build", "connector": "github.push"},
    {"description": "ship", "connector": "github.push"},
])
assert g.get("oracle").read().golden_path is not None
syntax = g.get("syntax_fixer")
fixed, _ = syntax.fix_entry("workorder", "workorder:x@github.pu#99.0!complete")
assert "@github.push" in fixed and "#10.00" in fixed and "!done" in fixed
backlog = g.get("backlog")
orders = g.get("workorders").parse("push more files")
backlog.defer(orders[0])
backlog.build_cube()
backlog.start_idle_miner(idle_seconds=0.05)
time.sleep(0.3)
backlog.stop_idle_miner()
assert backlog.chain.verify()

# Forge verify-until-green
forge = g.get("forge")
bp = forge.new_blueprint("smoke-bp")
forge.instantiate(bp, "player", "hero")
forge.instantiate(bp, "sink", "output")
bp.connect(("hero", "intent"), ("output", "in"))
result = forge.materialise(bp, era="extraction_now", target="godot", repair=True, max_rounds=2)
assert result["verification"]["accepted"]

# Persistence round-trip
from skeleton.deploy.harness import Harness
h1 = Harness(seed=42, snapshot_root=smoke_dir)
h1.boot()
h1.genesis.get("quad").ingest_document("persist-smoke", "Persistence keeps knowledge alive.")
h1.snapshot_state(name="smoke")
h2 = Harness(seed=42, snapshot_root=smoke_dir)
h2.boot(restore=False)
restored = h2.restore_state(name="smoke")
assert restored.get("kag", 0) > 0

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 11 phases, v35 over-achiever: control={d['control']:.2f} draw={d['energy']['draw']['total_w']:.0f}W atlas={atlas_summary['total']} caps, fleet={status['fleet']['registry']['devices']} devices)")
PY
