#!/usr/bin/env bash
# Smoke test the cockpit: full stack — 11 phases, federation, Context
# Fabric, Support System, and the high-intricacy OverseerEngineV2
# (fusion, forecasting, PID control, QoS arbitration, wear model).
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
assert health["subsystems"] >= 44, f"expected 44+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election", "fleet",
            "fabric", "workorders", "backlog", "planning", "queue", "oracle", "syntax_fixer", "cycle",
            "support", "loader", "agentic_rag", "overseer", "engine", "engine_v2"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# Engine V2: full telemetry tick at boot + controlled budget binding
engine_v2 = g.get("engine_v2")
assert engine_v2._ticks >= 1, "engine v2 never ticked"
status = engine_v2.status()
for key in ("device", "control", "wear", "last_tick", "consumers"):
    assert key in status, f"status missing {key}"
assert status["device"]["device_class"] in ("embedded", "mobile", "laptop", "workstation", "server")

# Tick produces fused channels, forecasts, wear, and a control decision
tick = engine_v2.tick()
d = tick.to_dict()
assert "fused" in d and "forecasts" in d and "wear" in d and "decision" in d
assert 0.05 <= d["decision"]["aggregate"] <= 1.0
assert len(d["decision"]["allocations"]) == 4, "QoS arbitration missing tiers"
assert d["decision"]["regime"] in ("idle", "interactive", "batch", "burst", "sustained")

# V2 budget is authoritative on the loader
loader = g.get("loader")
v2_cap = engine_v2.base_budget.scaled(d["decision"]["aggregate"]).max_resident_planes
assert loader.max_resident == v2_cap, f"loader cap {loader.max_resident} != v2 budget {v2_cap}"

# Tier shares sum to 1 and critical is always allowed
allocs = d["decision"]["allocations"]
assert abs(sum(a["share"] for a in allocs) - 1.0) < 0.01
critical = next(a for a in allocs if a["tier"] == "critical")
assert critical["allowed"] is True

# V1 engine still live
engine = g.get("engine")
assert engine.governor._stats["ticks"] >= 1

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

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 11 phases, engine v2 live: {status['device']['device_class']} regime={d['decision']['regime']} aggregate={d['decision']['aggregate']:.2f} wear={d['wear']['wear_index']:.3f})")
PY
