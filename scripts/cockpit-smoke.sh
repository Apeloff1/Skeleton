#!/usr/bin/env bash
# Smoke test the cockpit: full federation stack — messaging, consensus,
# KAG sync, cross-node routing, leader election, fleet coordination,
# plus the local chain: four-plane retrieval, Jeeves with citations,
# consolidation, persistence, and the forge verify-until-green loop.
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
assert health["subsystems"] >= 30, f"expected 30+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge",
            "galaxy", "galaxy_transport", "consensus", "kag_sync", "galaxy_bridge",
            "election", "fleet"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# Full federation stack between two live nodes
from skeleton.galaxy import GalaxyNode, NodeTransport
from skeleton.galaxy.consensus import ConsensusEngine
from skeleton.galaxy.kag_sync import KAGSync
from skeleton.galaxy.galaxy_bridge import GalaxyBridge
from skeleton.galaxy.election import LeaderElection
from skeleton.galaxy.fleet import FleetCoordinator
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
local_fleet = g.get("fleet")
try:
    got = []
    peer_transport.on("ping", lambda p: got.append(p))
    ok = local_transport.send(peer_transport.address, {"type": "ping", "data": "smoke"})
    assert ok and time.sleep(0.2) is None
    assert len(got) == 1

    g.get("galaxy")._registry.register("smoke-peer", peer_transport.address, capabilities={"reasoning"})
    peer._registry.register(g.get("galaxy").node_id, local_transport.address,
                            capabilities=set(g.get("galaxy")._capabilities))

    # Consensus + election
    proposal = local_consensus.propose("era.bind", {"era": "extraction_now"}, wait=True, timeout=3.0)
    assert proposal.status == "accepted"
    leader = local_election.call_election(timeout=3.0)
    assert leader == g.get("galaxy").node_id, f"wrong leader: {leader}"
    assert local_fleet.stats()["is_leader"] is True

    # Fleet tick: leader-initiated KAG gossip
    g.get("quad").ingest_document("smoke-fed", "The Forge produces blueprints for games.")
    ticked = local_fleet.tick(force=True)
    assert ticked, "fleet tick did not fire"
    assert local_fleet.stats()["ticks"] == 1

    # Direct sync too (peer has no fleet tick handler wired, use explicit gossip)
    peer_before = peer_kag.graph.stats()["triples"]
    local_sync.sync_now()
    time.sleep(0.6)
    assert peer_kag.graph.stats()["triples"] > peer_before, "KAG never synced"

    # Cross-node task routing
    from skeleton.agents import Task
    import uuid
    rtask = Task(task_id=str(uuid.uuid4())[:8], description="solve remotely")
    assert local_bridge.offer_remote(rtask, "reasoning")
    remote = local_bridge.wait_result(rtask.task_id, timeout=3.0)
    assert remote is not None and remote.status == "completed"
    assert "solve remotely" in remote.result["answer"]
finally:
    local_transport.stop(); peer_transport.stop()

# Forge: materialize + verify loop
forge = g.get("forge")
bp = forge.new_blueprint("smoke-bp")
forge.instantiate(bp, "player", "hero")
forge.instantiate(bp, "sink", "output")
bp.connect(("hero", "intent"), ("output", "in"))
result = forge.materialise(bp, era="extraction_now", target="godot", repair=True, max_rounds=2)
assert result["verification"]["accepted"]
assert result["verify_loop"]["stopped_reason"] == "accepted"

# Retrieval: vector RAG + four planes + self-populating KAG
from skeleton.memory.vector import VectorStore
assert isinstance(g.get("rag"), VectorStore)
quad = g.get("quad")
assert set(quad._planes.keys()) == {"rag", "cag", "mag", "kag"}
quad.ingest_document("smoke-doc", "Skeleton is a game engine. The Forge produces blueprints.")
kag = quad._planes["kag"]
assert kag.graph.stats()["triples"] > 0
results = quad.retrieve("what does the Forge produce?", k=5)
assert len(results) > 0 and "kag" in {r.plane for r in results}

# Local swarm bridge
from skeleton.agents import Task as LocalTask
import uuid as _uuid
mesh = g.get("mesh")
mesh.join({"reasoning"}, weight=2.0)
ltask = LocalTask(task_id=str(_uuid.uuid4())[:8], description="smoke task")
assert g.get("bridge").dispatch(ltask, "reasoning")
assert "mesh_agent_id" in ltask.metadata

# Jeeves: provider path + matrices + KAG citations
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
assert "citations" in reply, "reply missing citations"
assert len(reply["citations"]) > 0, "no citations returned despite KAG facts"
assert any("forge" in c["matched_entity"] for c in reply["citations"])

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

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 9 phases, fleet tick fired, leader elected, kag synced, task routed, citations live, jeeves={reply['provider']})")
PY
