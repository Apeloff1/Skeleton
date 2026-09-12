#!/usr/bin/env bash
# Smoke test the cockpit: full stack — 11 phases, federation, Context
# Fabric, Support System, EngineV35, and the deep layers:
# Byzantine fleet trust, chaos harness, causal oracle, DP memory.
set -euo pipefail

SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

python - "$SMOKE_DIR" <<'PY'
import sys, time
from skeleton.genesis import Genesis

smoke_dir = sys.argv[1]

g = Genesis(seed=42).boot()
health = g.health()

assert health["subsystems"] >= 50, f"expected 50+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress", "chaos",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election", "fleet", "byzantine",
            "fabric", "workorders", "backlog", "planning", "queue", "oracle", "syntax_fixer",
            "cycle", "causal",
            "support", "loader", "agentic_rag", "overseer", "engine", "engine_v2", "engine_v3", "engine_v35",
            "dp"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# Byzantine: signed envelopes verify, equivocation proven, trust weighted
byz = g.get("byzantine")
env = byz.propose({"action": "fleet.sync", "tick": 1})
assert env.verify(b"skeleton-fleet-key")
assert not env.verify(b"wrong-key")
from skeleton.galaxy.byzantine import SignedEnvelope
forged = SignedEnvelope.create("evil", 1, {"x": 1}, "v0", b"forged-key")
assert byz.receive_vote(forged, voter_secret=b"s-evil") is None
assert byz.trust.record("evil").score < 1.0

# Chaos: seeded storm replayable, experiment holds steady state
chaos = g.get("chaos")
from skeleton.resilience.chaos import ChaosSchedule, SteadyStateHypothesis
s1 = ChaosSchedule(seed=9).generate("storm", ["rag", "mesh"])
s2 = ChaosSchedule(seed=9).generate("storm", ["rag", "mesh"])
assert [(e.kind, e.target) for e in s1] == [(e.kind, e.target) for e in s2]
hyp = SteadyStateHypothesis()
hyp.expect("genesis_healthy", lambda: g.health()["healthy"], lambda v: v, "stays healthy")
report = chaos.run_experiment("drizzle", ["rag"], hyp, seed=4)
assert report.passed, f"chaos experiment failed: {report.to_dict()}"

# Causal: feed interleaved system series, learn edges, intervene, attribute
causal = g.get("causal")
for i in range(40):
    throttle = (i % 10) / 10.0
    quality = 0.7 * throttle + 0.05 * ((i * 7) % 3)
    causal.observe({"throttle": throttle, "quality": quality, "noise": (i % 5) / 5.0})
parents = causal.graph.parents("quality", min_strength=0.05)
assert any(e.src == "throttle" for e in parents), "throttle→quality edge not learned"
iv = causal.what_if("throttle", 1.0)
assert "quality" in iv.deltas
attr = causal.why("quality", 1.0)
assert len(attr.contributions) > 0

# DP: noised aggregates from live planes, budget enforced, no raw leak
dp = g.get("dp")
g.get("mag").record("dp-smoke", "private episode text", tags=["smoke", "dp"])
mag_adapter = dp.adapter("mag")
hist = mag_adapter.tag_histogram(epsilon=0.3)
assert hist is not None and "smoke" in hist
for k in hist.keys():
    assert "private" not in str(k)
count = mag_adapter.document_count(epsilon=0.2)
assert count is not None
spend = dp.accountant.stats()["spent_total"]
assert spend > 0
acc = dp.accountant
acc.session_budget = acc._spent_total  # simulate exhaustion at current spend
assert mag_adapter.document_count(epsilon=0.2) is None, "budget stop failed"

# V3.5 + full chain still green
v35 = g.get("engine_v35")
tick = v35.tick()
d = tick.to_dict()
assert 0.05 <= d["control"] <= 1.0 and d["fleet"]["attached"] is True

fabric = g.get("fabric")
fabric.distill("push files to github. search the web for docs. build pdf.", 1500)
support = g.get("support")
out = support.support_cycle(fabric)
assert len(out["loaded"]) >= 1
g.get("quad").ingest_document("smoke-doc", "Skeleton is a game engine. The Forge produces blueprints.")
rag = g.get("agentic_rag")
result = rag.retrieve("how does the forge relate to blueprints?")
assert result.query_class == "relational" and result.coverage > 0

from skeleton.api.server import ServerState
state = ServerState()
state.wire_from_genesis(g)
session = state.jeeves.open_session("smoke-user")
r1 = state.jeeves.ask(session.session_id, "push these files to github")
assert "cycle" in r1 and r1["cycle"]["orders_executed"] >= 1

forge = g.get("forge")
bp = forge.new_blueprint("smoke-bp")
forge.instantiate(bp, "player", "hero")
forge.instantiate(bp, "sink", "output")
bp.connect(("hero", "intent"), ("output", "in"))
result = forge.materialise(bp, era="extraction_now", target="godot", repair=True, max_rounds=2)
assert result["verification"]["accepted"]

from skeleton.deploy.harness import Harness
h1 = Harness(seed=42, snapshot_root=smoke_dir)
h1.boot()
h1.genesis.get("quad").ingest_document("persist-smoke", "Persistence keeps knowledge alive.")
h1.snapshot_state(name="smoke")
h2 = Harness(seed=42, snapshot_root=smoke_dir)
h2.boot(restore=False)
restored = h2.restore_state(name="smoke")
assert restored.get("kag", 0) > 0

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 11 phases, deep layers live: byzantine signed, chaos passed, causal edges={len(causal.graph.edges())}, dp spend={spend:.2f})")
PY
