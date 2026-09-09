#!/usr/bin/env bash
# Smoke test the cockpit: full stack — 10 genesis phases, federation
# (messaging, consensus, election, fleet, KAG sync, routing), local chain
# (4-plane retrieval, Jeeves citations, consolidation, persistence,
# forge verify-until-green), and the Context Fabric (work orders, backlog
# chain, 18-system queue, oracle fate matrix, syntax repair).
set -euo pipefail

SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

python - "$SMOKE_DIR" <<'PY'
import sys, time
from skeleton.genesis import Genesis

smoke_dir = sys.argv[1]

g = Genesis(seed=42).boot()
health = g.health()

assert "forge" in health["phases"], f"forge phase missing: {health['phases']}"
assert "galaxy" in health["phases"], f"galaxy phase missing: {health['phases']}"
assert "contexts" in health["phases"], f"contexts phase missing: {health['phases']}"
assert "cortex" in health["phases"]
assert health["subsystems"] >= 37, f"expected 37+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0, f"invariants violated: {health['invariant_violations']}"

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election", "fleet",
            "fabric", "workorders", "backlog", "planning", "queue", "oracle", "syntax_fixer"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# Context Fabric: full distill cycle at max-token scale
fabric = g.get("fabric")
result = fabric.distill(
    "Plan confirmed. Push these files to github. Then search the web for the API docs. "
    "Build pdf of the final report. The architecture holds together beautifully.",
    token_count=4096,
)
assert result["orders_active"] >= 3, f"expected 3+ orders, got {result['orders_active']}"
assert result["queued"] >= 3, "orders never queued"

# Work orders parse ONLY external workload
orders = g.get("workorders").parse("The design is elegant. Push the batch. Lovely work.")
assert len(orders) == 1 and orders[0].connector == "github.push"

# MAG enhancement: orders carry episodic context
g.get("mag").record("ep-wo", "earlier github push landed 5 files", tags=["github.push"])
g.get("workorders").enhance(orders[0])
assert len(orders[0].mag_context) > 0, "MAG never enhanced the order"

# Backlog: defer → cube → idle-mined chain verifies
backlog = g.get("backlog")
backlog.defer(orders[0])
backlog.build_cube()
backlog.start_idle_miner(idle_seconds=0.05)
time.sleep(0.3)
backlog.stop_idle_miner()
assert backlog.chain.verify(), "work chain failed verification"
assert backlog.summary()["blocks_sealed"] >= 1, "no blocks sealed while idle"

# Queue: all 18 probability systems score every item
queue = g.get("queue")
card = queue.score({"priority": 5.0, "attempts": 4, "done": 3})
assert len(card) == 18, f"expected 18 systems, got {len(card)}"
assert all(0.0 <= v <= 1.0 for v in card.values())

# Planning + Oracle: golden path exists and narrates positively
fabric.planning.decompose("finish the product", [
    {"description": "gather requirements"},
    {"description": "build core", "connector": "github.push"},
    {"description": "verify quality"},
    {"description": "ship it", "connector": "github.push"},
])
reading = g.get("oracle").read()
assert reading.golden_path is not None, "no golden path found"
narration = reading.narrate()
assert "golden path" in narration.lower()

# Syntax fixer: repairs across the spider web
syntax = g.get("syntax_fixer")
fixed, issues = syntax.fix_entry("workorder", "workorder:x1@github.pu#99.0!complete")
assert "@github.push" in fixed and "#10.00" in fixed and "!done" in fixed
assert syntax.stats()["planes_connected"] >= 4

# Interjected summary fires after completion
ctx = g.get("workorders").context
if ctx.slots:
    g.get("workorders").mark(ctx.slots[0].order_id, "done")
    summary = g.get("workorders").interjected_summary()
    assert summary is not None and "landed" in summary

# Forge: materialize + verify loop (local chain still green)
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

# Jeeves: provider + matrices + citations
from skeleton.api.server import ServerState
state = ServerState()
state.wire_from_genesis(g)
session = state.jeeves.open_session("smoke-user")
reply = state.jeeves.ask(session.session_id, "what does the forge build?")
assert reply["provider"] in ("local-echo", "openai", "anthropic")
assert len(reply.get("citations", [])) > 0
assert set(state.jeeves.matrices().keys()) == {"sam", "clom", "krem"}

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

# Cortex observed context events
from skeleton.cortex import live
status = live.status()
assert status["live"] and status["events_captured"] > 0

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 10 phases, fabric live: {result['orders_active']} orders, {len(card)} systems, golden path, chain sealed, jeeves={reply['provider']})")
PY
