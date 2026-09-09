#!/usr/bin/env bash
# Smoke test the cockpit: full stack — 10 genesis phases, federation
# (messaging, consensus, election, fleet, KAG sync, routing), local chain
# (4-plane retrieval, Jeeves citations, consolidation, persistence,
# forge verify-until-green), the Context Fabric (work orders, backlog
# chain, 18-system queue, oracle fate matrix, syntax repair), and the
# ResponseCycle driving it all through live conversation.
set -euo pipefail

SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

python - "$SMOKE_DIR" <<'PY'
import sys, time
from skeleton.genesis import Genesis

smoke_dir = sys.argv[1]

g = Genesis(seed=42).boot()
health = g.health()

assert "contexts" in health["phases"], f"contexts phase missing: {health['phases']}"
assert "forge" in health["phases"] and "galaxy" in health["phases"] and "cortex" in health["phases"]
assert health["subsystems"] >= 38, f"expected 38+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election", "fleet",
            "fabric", "workorders", "backlog", "planning", "queue", "oracle", "syntax_fixer", "cycle"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# ResponseCycle through live Jeeves conversation: turn 1 parses + executes,
# turn 2 carries the interjection
from skeleton.api.server import ServerState
state = ServerState()
state.wire_from_genesis(g)
assert state.jeeves._cycle is not None, "jeeves missing cycle"
assert state.jeeves._cycle._fabric is g.get("fabric"), "cycle bound to wrong fabric"

session = state.jeeves.open_session("smoke-cycle-user")
r1 = state.jeeves.ask(session.session_id, "push these files to github and search the web for docs")
assert "cycle" in r1, "reply missing cycle report"
assert r1["cycle"]["orders_parsed"] >= 1, f"nothing parsed: {r1['cycle']}"
assert r1["cycle"]["orders_executed"] >= 1, "nothing executed between turns"

r2 = state.jeeves.ask(session.session_id, "what is next?")
assert "interjection" in r2, "no interjection on follow-up turn"
assert "landed" in r2["content"], "interjection not prepended to reply"

# Jeeves still grounded: provider, citations, matrices
assert r1["provider"] in ("local-echo", "openai", "anthropic")
assert set(state.jeeves.matrices().keys()) == {"sam", "clom", "krem"}
assert state.jeeves_sam.stats()["terms"] > 0

# Fabric planes still healthy under the cycle
fabric = g.get("fabric")
assert fabric.workorders.stats()["completed"] >= 1
queue = g.get("queue")
card = queue.score({"priority": 5.0, "attempts": 4, "done": 3})
assert len(card) == 18

# Backlog chain: cube + idle mine + verify
backlog = g.get("backlog")
orders = g.get("workorders").parse("push more files")
backlog.defer(orders[0])
backlog.build_cube()
backlog.start_idle_miner(idle_seconds=0.05)
time.sleep(0.3)
backlog.stop_idle_miner()
assert backlog.chain.verify()

# Oracle: golden path + positive narration
fabric.planning.decompose("finish the product", [
    {"description": "gather requirements"},
    {"description": "build core", "connector": "github.push"},
    {"description": "verify quality"},
    {"description": "ship it", "connector": "github.push"},
])
reading = g.get("oracle").read()
assert reading.golden_path is not None
assert "golden path" in reading.narrate().lower()

# Syntax fixer repairs across the web
syntax = g.get("syntax_fixer")
fixed, issues = syntax.fix_entry("workorder", "workorder:x1@github.pu#99.0!complete")
assert "@github.push" in fixed and "#10.00" in fixed and "!done" in fixed

# Forge: materialize + verify loop
forge = g.get("forge")
bp = forge.new_blueprint("smoke-bp")
forge.instantiate(bp, "player", "hero")
forge.instantiate(bp, "sink", "output")
bp.connect(("hero", "intent"), ("output", "in"))
result = forge.materialise(bp, era="extraction_now", target="godot", repair=True, max_rounds=2)
assert result["verification"]["accepted"]

# Retrieval: 4 planes + self-populating KAG
quad = g.get("quad")
assert set(quad._planes.keys()) == {"rag", "cag", "mag", "kag"}
quad.ingest_document("smoke-doc", "Skeleton is a game engine. The Forge produces blueprints.")
results = quad.retrieve("what does the Forge produce?", k=5)
assert len(results) > 0 and "kag" in {r.plane for r in results}

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

# Cortex observed cycle events
from skeleton.cortex import live
status = live.status()
assert status["live"] and status["events_captured"] > 0

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 10 phases, cycle live: turn1={r1['cycle']['orders_executed']} executed, interjection on turn2, golden path, chain sealed)")
PY
