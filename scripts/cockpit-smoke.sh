#!/usr/bin/env bash
# Smoke test the cockpit: full stack — 11 phases, federation, Context
# Fabric, Support System, and the paramount OverseerEngineV3
# (system ID, MPC with hard walls, digital twin, meta-cognition).
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
assert health["subsystems"] >= 45, f"expected 45+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election", "fleet",
            "fabric", "workorders", "backlog", "planning", "queue", "oracle", "syntax_fixer", "cycle",
            "support", "loader", "agentic_rag", "overseer", "engine", "engine_v2", "engine_v3"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# Engine V3: paramount telemetry at boot + MPC budget authority
v3 = g.get("engine_v3")
assert v3._ticks >= 1, "engine v3 never ticked"
status = v3.status()
for key in ("device", "control", "setpoints", "sysid", "mpc", "twin", "meta", "wear", "consumers"):
    assert key in status, f"status missing {key}"
assert status["device"]["device_class"] in ("embedded", "mobile", "laptop", "workstation", "server")

# Ticks build identified models and MPC plans with hard walls
for _ in range(6):
    tick = v3.tick()
d = tick.to_dict()
assert len(d["models"]) > 0, "no identified models"
assert all(s["samples"] >= 1 for s in d["models"].values())
assert 0.05 <= d["control"] <= 1.0
assert "trajectory" in d["mpc"] and d["mpc"]["candidates"] >= 1
assert isinstance(d["anomalies"], list)
assert 0.0 <= d["trust"] <= 1.0
assert isinstance(d["fallback"], bool)

# V3 MPC budget is authoritative on the loader
loader = g.get("loader")
v3_cap = v3.base_budget.scaled(d["control"]).max_resident_planes
assert loader.max_resident == v3_cap, f"loader cap {loader.max_resident} != v3 budget {v3_cap}"

# Meta-cognition: scorecards exist after error observation, trust computable
meta = v3.meta
assert meta.trust() >= 0.0

# V1 + V2 engines still live alongside
assert g.get("engine").governor._stats["ticks"] >= 1
assert g.get("engine_v2")._ticks >= 1

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

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 11 phases, engine v3 paramount: {status['device']['device_class']} control={d['control']:.2f} mpc={d['mpc']['trajectory']} trust={d['trust']} regime={d['regime']})")
PY
