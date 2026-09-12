#!/usr/bin/env bash
# Smoke test the cockpit: full stack — 12 phases with the foundation
# bedrock (Merkle DAG, journaled bus, ocap, temporal lattice) plus the
# federation, Context Fabric, Support System, EngineV35, and deep layers.
set -euo pipefail

SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

python - "$SMOKE_DIR" <<'PY'
import sys, time
from skeleton.genesis import Genesis

smoke_dir = sys.argv[1]

g = Genesis(seed=42).boot()
health = g.health()

assert g.report.phases[0] == "foundation", f"foundation not first: {g.report.phases[0]}"
assert health["subsystems"] >= 56, f"expected 56+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0
assert health["journal_integrity"] is True, "journal hash chain broken"
assert health["temporal_healthy"] is True, "temporal invariant violated"

required = ["dag", "journal", "replay", "ocap", "membrane", "temporal",
            "lattice", "rag", "trinity", "orchestrator", "mesh", "fortress", "chaos",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election", "fleet", "byzantine",
            "fabric", "workorders", "backlog", "planning", "queue", "oracle", "syntax_fixer",
            "cycle", "causal",
            "support", "loader", "agentic_rag", "overseer", "engine", "engine_v2", "engine_v3", "engine_v35",
            "dp"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# Merkle DAG: content addressing, dedup, tamper evidence, provenance
dag = g.get("dag")
h1 = dag.put({"artifact": "blueprint-v1", "files": 5})
h2 = dag.put({"files": 5, "artifact": "blueprint-v1"})
assert h1 == h2, "content addressing failed"
assert dag.stats()["deduped"] >= 1
assert dag.verify(h1)
dag._nodes[h1].payload["files"] = 6
assert not dag.verify(h1), "tamper not detected"
dag._nodes.pop(h1)  # cleanup the tampered node
h_parent = dag.put({"gen": 0})
h_child = dag.put({"gen": 1}, links=[h_parent])
assert len(dag.ancestry(h_child)) == 2

# Journal + replay: every event captured, deterministic reconstruction
journal = g.get("journal")
assert len(journal) > 0
topics = [e.topic for e in journal.slice(0)]
assert "kernel.genesis.booted" in topics
replay = g.get("replay")
replay.on("kernel.genesis.booted", lambda e, s: s.update(booted=True))
state = replay.replay()
assert state.get("booted") is True, "replay missed the boot event"

# OCap: attenuation, revocation, membrane
ocap = g.get("ocap")
class Probe:
    def read(self):
        return "probe-data"
    def write(self, v):
        return v
root = ocap.mint("probe", {"read", "write"}, target=Probe())
reader = ocap.attenuate(root, rights={"read"})
assert ocap.invoke(reader, "read") == "probe-data"
try:
    ocap.invoke(reader, "write", "x")
    raise AssertionError("attenuation failed to block write")
except PermissionError:
    pass
ocap.revoke(reader)
try:
    ocap.invoke(reader, "read")
    raise AssertionError("revocation failed")
except PermissionError:
    pass

# Temporal lattice: boot invariant satisfied, violation traces work
temporal = g.get("temporal")
violations = temporal.violations()
boot_violations = [v for v in violations if v.invariant == "genesis_boots_eventually"]
assert boot_violations == [], f"boot invariant violated: {boot_violations}"
temporal.never("smoke_no_panic", lambda e: e.get("topic", "").endswith("panic"))
assert temporal.healthy()

# V3.5 + federation still green
v35 = g.get("engine_v35")
tick = v35.tick()
d = tick.to_dict()
assert 0.05 <= d["control"] <= 1.0 and d["fleet"]["attached"] is True

byz = g.get("byzantine")
env = byz.propose({"action": "fleet.sync", "tick": 1})
assert env.verify(b"skeleton-fleet-key")

# Full local chain
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

queue = g.get("queue")
assert len(queue.score({"priority": 5.0})) == 18
fabric.planning.decompose("finish product", [
    {"description": "build", "connector": "github.push"},
    {"description": "ship", "connector": "github.push"},
])
assert g.get("oracle").read().golden_path is not None

causal = g.get("causal")
for i in range(30):
    causal.observe({"throttle": (i % 10) / 10.0, "quality": 0.7 * ((i % 10) / 10.0)})
assert len(causal.graph.edges()) > 0

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

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 12 phases, bedrock live: dag={dag.stats()['nodes']} nodes, journal={len(journal)} entries intact, ocap enforced, temporal healthy)")
PY
