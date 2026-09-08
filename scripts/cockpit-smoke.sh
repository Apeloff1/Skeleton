#!/usr/bin/env bash
# Smoke test the cockpit: boot genesis, hit health, verify handles,
# four-plane retrieval with self-populating KAG, Jeeves provider path,
# memory matrices, swarm-agents bridge, persistence round-trip,
# genesis-wired forge with verify-until-green, consolidation cycle,
# galaxy transport, cross-node consensus, federated KAG sync,
# cross-node task routing, and leader election.
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
assert health["subsystems"] >= 29, f"expected 29+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# Galaxy: messaging, consensus, KAG sync, task routing, AND leader election
from skeleton.galaxy import GalaxyNode, NodeTransport
from skeleton.galaxy.consensus import ConsensusEngine
from skeleton.galaxy.kag_sync import KAGSync
from skeleton.galaxy.galaxy_bridge import GalaxyBridge
from skeleton.galaxy.election import LeaderElection
from skeleton.retrieval.kag import KnowledgeGraph, KAGRetriever
from skeleton.swarm.mesh import SwarmMesh
from skeleton.agents.bridge import MeshBridge
peer = GalaxyNode(node_id="smoke-peer")
peer.add_capability("reasoning")
peer_transport = NodeTransport(peer).start()
peer_consensus = ConsensusEngine(peer, peer_transport)
peer_election = LeaderElection(peer, peer_transport, peer_consensus)
peer_kag = KAGRetriever(KnowledgeGraph())
peer_sync = KAGSync(peer_kag, peer, peer_transport, consensus=peer_consensus)
peer_bridge = GalaxyBridge(MeshBridge(SwarmMesh()), peer, peer_transport)
peer_bridge.serve("reasoning", lambda p: {"answer": f"remote handled: {p['description']}"})
local_transport = g.get("galaxy_transport").start()
local_consensus = g.get("consensus")
local_sync = g.get("kag_sync")
local_bridge = g.get("galaxy_bridge")
local_election = g.get("election")
try:
    got = []
    peer_transport.on("ping", lambda p: got.append(p))
    ok = local_transport.send(peer_transport.address, {"type": "ping", "data": "smoke"})
    assert ok, "galaxy send failed"
    time.sleep(0.2)
    assert len(got) == 1, "peer never received message"

    g.get("galaxy")._registry.register("smoke-peer", peer_transport.address, capabilities={"reasoning"})
    peer._registry.register(g.get("galaxy").node_id, local_transport.address,
                            capabilities=set(g.get("galaxy")._capabilities))

    # Consensus
    proposal = local_consensus.propose("era.bind", {"era": "extraction_now"}, wait=True, timeout=3.0)
    assert proposal.status == "accepted", f"consensus failed: {proposal.status}"

    # Leader election: local node has 3 capabilities vs peer's 1 → local wins
    leader = local_election.call_election(timeout=3.0)
    assert leader == g.get("galaxy").node_id, f"wrong leader: {leader}"
    assert local_election.is_leader()
    time.sleep(0.4)
    assert peer_election.state.leader_id == g.get("galaxy").node_id, "peer never installed leader"

    # Federated KAG sync
    peer_before = peer_kag.graph.stats()["triples"]
    g.get("quad").ingest_document("smoke-fed", "The Forge produces blueprints for games.")
    local_sync.sync_now()
    time.sleep(0.6)
    assert peer_kag.graph.stats()["triples"] > peer_before, "KAG never synced to peer"

    # Cross-node task routing
    from skeleton.agents import Task
    import uuid
    rtask = Task(task_id=str(uuid.uuid4())[:8], description="solve remotely")
    offered = local_bridge.offer_remote(rtask, "reasoning")
    assert offered, "remote offer failed"
    remote = local_bridge.wait_result(rtask.task_id, timeout=3.0)
    assert remote is not None and remote.status == "completed", f"remote task failed: {remote and remote.status}"
    assert "solve remotely" in remote.result["answer"]
finally:
    local_transport.stop(); peer_transport.stop()

# Genesis-wired forge: materialize + verify loop
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

# Self-populating KAG
quad.ingest_document("smoke-doc", "Skeleton is a game engine. The Forge produces blueprints.")
kag = quad._planes["kag"]
assert kag.graph.stats()["triples"] > 0, "KAG did not self-populate from ingestion"
results = quad.retrieve("what does the Forge produce?", k=5)
assert len(results) > 0 and "kag" in {r.plane for r in results}

# Swarm-agents bridge: local dispatch
from skeleton.agents import Task as LocalTask
import uuid as _uuid
mesh = g.get("mesh")
mesh.join({"reasoning"}, weight=2.0)
bridge = g.get("bridge")
ltask = LocalTask(task_id=str(_uuid.uuid4())[:8], description="smoke task")
assert bridge.dispatch(ltask, "reasoning")
assert "mesh_agent_id" in ltask.metadata

# Jeeves provider path + memory matrices
from skeleton.api.server import ServerState
state = ServerState()
state.wire_from_genesis(g)
session = state.jeeves.open_session("smoke-user")
reply = state.jeeves.ask(session.session_id, "what does the forge build?")
assert reply["provider"] in ("local-echo", "openai", "anthropic")
assert state.jeeves_sam.stats()["terms"] > 0
assert state.jeeves_clom.stats()["records"] > 0
assert state.jeeves_krem.stats()["concepts"] > 0
assert set(state.jeeves.matrices().keys()) == {"sam", "clom", "krem"}

# Consolidation cycle
from skeleton.memory.consolidation import wire_from_genesis
cycle = wire_from_genesis(g, state.jeeves, bus=g.bus)
for concept in list(state.jeeves.krem._cells)[:2]:
    state.jeeves.krem._cells[concept].last_seen = time.time() - (state.jeeves.krem.HALF_LIFE_HOURS * 10 * 3600)
report = cycle.cycle()
assert "due" in report and "scheduled" in report

# Live cortex observed forge + consolidation events
from skeleton.cortex import live
status = live.status()
assert status["live"] and status["events_captured"] > 0
assert len(live.get_live().recent_events("forge", n=5)) > 0
assert len(live.get_live().recent_events("memory.consolidation.cycle", n=5)) > 0

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
assert h2.genesis.get("quad")._planes["kag"].graph.stats()["triples"] > 0
mresult = h2.materialize("smoke-harness-bp")
assert "blueprint_id" in mresult

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 9 phases, leader elected, consensus accepted, kag synced, remote task routed, godot verified)")
PY
