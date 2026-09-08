#!/usr/bin/env bash
# Smoke test the cockpit: boot genesis, hit health, verify handles,
# four-plane retrieval with self-populating KAG, Jeeves provider path,
# memory matrices, swarm-agents bridge, persistence round-trip,
# genesis-wired forge with verify-until-green, consolidation cycle,
# galaxy transport, cross-node consensus, and federated KAG sync.
set -euo pipefail

SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

python - "$SMOKE_DIR" <<'PY'
import sys, time
from skeleton.genesis import Genesis

smoke_dir = sys.argv[1]

g = Genesis(seed=42).boot()
health = g.health()

assert "kernel" in health["phases"]
assert "forge" in health["phases"], f"forge phase missing: {health['phases']}"
assert "galaxy" in health["phases"], f"galaxy phase missing: {health['phases']}"
assert "cortex" in health["phases"]
assert health["subsystems"] >= 27, f"expected 27+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# Galaxy: live messaging, cross-node consensus, AND federated KAG sync
from skeleton.galaxy import GalaxyNode, NodeTransport
from skeleton.galaxy.consensus import ConsensusEngine
from skeleton.galaxy.kag_sync import KAGSync
from skeleton.retrieval.kag import KnowledgeGraph, KAGRetriever
peer = GalaxyNode(node_id="smoke-peer")
peer_transport = NodeTransport(peer).start()
peer_consensus = ConsensusEngine(peer, peer_transport)
peer_kag = KAGRetriever(KnowledgeGraph())
peer_sync = KAGSync(peer_kag, peer, peer_transport, consensus=peer_consensus)
local_transport = g.get("galaxy_transport").start()
local_consensus = g.get("consensus")
local_sync = g.get("kag_sync")
try:
    got = []
    peer_transport.on("ping", lambda p: got.append(p))
    ok = local_transport.send(peer_transport.address, {"type": "ping", "data": "smoke"})
    assert ok, "galaxy send failed"
    time.sleep(0.2)
    assert len(got) == 1, "peer never received message"

    # Cross-node consensus
    g.get("galaxy")._registry.register("smoke-peer", peer_transport.address)
    peer._registry.register(g.get("galaxy").node_id, local_transport.address)
    proposal = local_consensus.propose("era.bind", {"era": "extraction_now"}, wait=True, timeout=3.0)
    assert proposal.status == "accepted", f"consensus failed: {proposal.status}"

    # Federated KAG sync: local ingest propagates to the peer's graph
    local_kag = g.get("quad")._planes["kag"]
    before = peer_kag.graph.stats()["triples"]
    local_sync.sync_now()  # gossip digest → peer requests missing → triples flow back
    # Ingest first so there's something to sync
    g.get("quad").ingest_document("smoke-fed", "The Forge produces blueprints for games.")
    local_sync.sync_now()
    time.sleep(0.6)
    after = peer_kag.graph.stats()["triples"]
    assert after > before, f"KAG never synced to peer: {before} → {after}"
finally:
    local_transport.stop(); peer_transport.stop()

# Genesis-wired forge: materialize through it and verify the loop accepts
forge = g.get("forge")
bp = forge.new_blueprint("smoke-bp")
forge.instantiate(bp, "player", "hero")
forge.instantiate(bp, "sink", "output")
bp.connect(("hero", "intent"), ("output", "in"))
result = forge.materialise(bp, era="extraction_now", target="godot", repair=True, max_rounds=2)
assert result["verification"]["accepted"], f"godot materialise rejected: {result['verification'].get('reason')}"
assert result["verify_loop"]["stopped_reason"] == "accepted"

# Retrieval: vector RAG default + four quad planes
from skeleton.memory.vector import VectorStore
assert isinstance(g.get("rag"), VectorStore), "RAG plane should be VectorStore"
quad = g.get("quad")
assert set(quad._planes.keys()) == {"rag", "cag", "mag", "kag"}, f"quad planes: {quad._planes.keys()}"

# Self-populating KAG: ingestion extracts triples automatically
quad.ingest_document("smoke-doc", "Skeleton is a game engine. The Forge produces blueprints.")
kag = quad._planes["kag"]
assert kag.graph.stats()["triples"] > 0, "KAG did not self-populate from ingestion"

results = quad.retrieve("what does the Forge produce?", k=5)
assert len(results) > 0, "quad retrieval returned nothing"
assert "kag" in {r.plane for r in results}, "KAG plane did not contribute"

# Swarm-agents bridge: coordinator task rides the live mesh
from skeleton.agents import Task
import uuid
mesh = g.get("mesh")
mesh.join({"reasoning"}, weight=2.0)
bridge = g.get("bridge")
task = Task(task_id=str(uuid.uuid4())[:8], description="smoke task")
assert bridge.dispatch(task, "reasoning"), "bridge dispatch failed"
assert "mesh_agent_id" in task.metadata

# Jeeves provider path + memory matrices through API server state
from skeleton.api.server import ServerState
state = ServerState()
state.wire_from_genesis(g)
assert state.jeeves_sam is not None and state.jeeves_clom is not None and state.jeeves_krem is not None
session = state.jeeves.open_session("smoke-user")
reply = state.jeeves.ask(session.session_id, "what does the forge build?")
assert reply["provider"] in ("local-echo", "openai", "anthropic")
assert state.jeeves_sam.stats()["terms"] > 0, "SAM observed nothing"
assert state.jeeves_clom.stats()["records"] > 0, "CLOM recorded nothing"
assert state.jeeves_krem.stats()["concepts"] > 0, "KREM tracked nothing"
matrices = state.jeeves.matrices()
assert set(matrices.keys()) == {"sam", "clom", "krem"}

# Consolidation cycle: KREM due-refresh closes the retention loop
from skeleton.memory.consolidation import wire_from_genesis
cycle = wire_from_genesis(g, state.jeeves, bus=g.bus)
for concept in list(state.jeeves.krem._cells)[:2]:
    state.jeeves.krem._cells[concept].last_seen = time.time() - (state.jeeves.krem.HALF_LIFE_HOURS * 10 * 3600)
report = cycle.cycle()
assert "due" in report and "scheduled" in report
assert cycle.stats()["cycles"] == 1

# Live cortex observed the traffic (forge + consolidation events)
from skeleton.cortex import live
status = live.status()
assert status["live"] and status["events_captured"] > 0
forge_events = live.get_live().recent_events("forge", n=5)
assert len(forge_events) > 0, "cortex saw no forge events"
consolidation_events = live.get_live().recent_events("memory.consolidation.cycle", n=5)
assert len(consolidation_events) > 0, "cortex saw no consolidation events"

# Persistence round-trip: snapshot, simulate restart, restore, verify
from skeleton.deploy.harness import Harness

h1 = Harness(seed=42, snapshot_root=smoke_dir)
h1.boot()
h1.genesis.get("quad").ingest_document("persist-smoke", "Persistence keeps knowledge alive.")
h1.snapshot_state(name="smoke")

h2 = Harness(seed=42, snapshot_root=smoke_dir)
h2.boot(restore=False)
restored = h2.restore_state(name="smoke")
assert restored.get("kag", 0) > 0, f"nothing restored: {restored}"
kag2 = h2.genesis.get("quad")._planes["kag"]
assert kag2.graph.stats()["triples"] > 0, "restored KAG is empty"

# Harness materialize rides the genesis forge handle
mresult = h2.materialize("smoke-harness-bp")
assert "blueprint_id" in mresult

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 9 phases, consensus accepted, kag synced, godot verified, jeeves={reply['provider']}, persistence OK)")
PY
