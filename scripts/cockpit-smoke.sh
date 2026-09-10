#!/usr/bin/env bash
# Smoke test the cockpit: full stack — 11 phases, federation, Context
# Fabric with ResponseCycle, Support System, and the hardware-specialized
# OverseerEngine (device classification, governor throttles, budget binding).
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
assert health["subsystems"] >= 43, f"expected 43+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election", "fleet",
            "fabric", "workorders", "backlog", "planning", "queue", "oracle", "syntax_fixer", "cycle",
            "support", "loader", "agentic_rag", "overseer", "engine"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# OverseerEngine: device classified, governor ticked at boot, budgets bound
engine = g.get("engine")
device = engine.device()
assert device["profile"]["device_class"] in ("embedded", "mobile", "laptop", "workstation", "server")
assert device["profile"]["cpu_cores"] >= 1
assert engine.governor._stats["ticks"] >= 1, "engine never ticked"
consumers = engine.governor.enforcer.consumers()
assert "loading_queue" in consumers and "priority_queue" in consumers and "backlog_miner" in consumers

# Budget binding actually applied: loader caps follow the budget, not defaults
loader = g.get("loader")
budget_cap = engine.governor.base_budget.scaled(engine.governor._active_throttle).max_resident_planes
assert loader.max_resident == budget_cap, f"loader cap {loader.max_resident} != budget {budget_cap}"

# Engine verdict + equilibrium surface
verdict = engine.engine_tick()
assert verdict.state in ("thriving", "stable", "strained", "critical")
eq = engine.equilibrium()
assert "pressure" in eq and "throttle" in eq
assert 0.0 <= eq["throttle"] <= 1.0

# Support cycle still live under the engine
fabric = g.get("fabric")
fabric.distill("push files to github. search the web for docs. build pdf.", 1500)
support = g.get("support")
out = support.support_cycle(fabric)
assert len(out["loaded"]) >= 1

# Agentic RAG classified retrieval
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

# Fabric planes: 18 systems, golden path, syntax repair
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

# Backlog chain seals while idle
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

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 11 phases, engine live: {device['profile']['device_class']} @ throttle {eq['throttle']}, verdict={verdict.state})")
PY
