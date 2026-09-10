#!/usr/bin/env bash
# Smoke test the cockpit: full stack — 11 genesis phases, federation,
# local chain, Context Fabric with ResponseCycle, and the Support System
# (lazy support planes via LoadingQueue, Agentic RAG, Overseer graphs).
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
assert "contexts" in health["phases"] and "cortex" in health["phases"]
assert health["subsystems"] >= 42, f"expected 42+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election", "fleet",
            "fabric", "workorders", "backlog", "planning", "queue", "oracle", "syntax_fixer", "cycle",
            "support", "loader", "agentic_rag", "overseer"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# LoadingQueue: support planes are lazy — nothing resident until pressure
loader = g.get("loader")
assert len(loader.resident_planes()) == 0, "support planes should be lazy at boot"
fabric = g.get("fabric")
fabric.distill("push files to github. search the web for docs. build pdf of the report.", 1500)
support = g.get("support")
out = support.support_cycle(fabric)
assert len(out["loaded"]) >= 1, "no support plane loaded under pressure"
assert len(loader.resident_planes()) <= loader.max_resident, "loader exceeded resident cap"
assert "verdict" in out

# Agentic RAG: classified, covered, traced, learning
g.get("quad").ingest_document("smoke-rag", "The Forge produces blueprints. Skeleton is a game engine.")
rag = g.get("agentic_rag")
result = rag.retrieve("how does the forge relate to blueprints?")
assert result.query_class == "relational", f"misclassified: {result.query_class}"
assert result.coverage > 0 and len(result.results) > 0
assert len(result.trace) > 0
assert len(rag.accuracy()) > 0, "agent learned nothing"

# Overseer: graphs feed from events, verdict coheres, equilibrium reports
overseer = g.get("overseer")
overseer.observe_event("organism.health.checked", {"checks": {"rag": {"healthy": True}}})
verdict = overseer.oversight_cycle()
assert verdict.state in ("thriving", "stable", "strained", "critical")
eq = overseer.equilibrium()
assert "pressure" in eq
assert overseer.fate.alignment() >= 0.0

# ResponseCycle through Jeeves: turn1 executes, turn2 interjects
from skeleton.api.server import ServerState
state = ServerState()
state.wire_from_genesis(g)
session = state.jeeves.open_session("smoke-user")
r1 = state.jeeves.ask(session.session_id, "push these files to github")
assert "cycle" in r1 and r1["cycle"]["orders_executed"] >= 1
r2 = state.jeeves.ask(session.session_id, "what next?")
assert "interjection" in r2

# Fabric planes: queue 18 systems, oracle golden path, syntax repair
queue = g.get("queue")
assert len(queue.score({"priority": 5.0})) == 18
fabric.planning.decompose("finish product", [
    {"description": "build", "connector": "github.push"},
    {"description": "ship", "connector": "github.push"},
])
reading = g.get("oracle").read()
assert reading.golden_path is not None
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

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 11 phases, support live: {len(out['loaded'])} planes loaded, rag={result.query_class}, verdict={verdict.state})")
PY
