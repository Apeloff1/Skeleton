#!/usr/bin/env bash
# Smoke test the cockpit: boot genesis, hit health, verify handles,
# four-plane retrieval with self-populating KAG, Jeeves provider path,
# memory matrices, swarm-agents bridge, persistence round-trip,
# and the genesis-wired forge with verify-until-green.
set -euo pipefail

SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

python - "$SMOKE_DIR" <<'PY'
import sys
from skeleton.genesis import Genesis

smoke_dir = sys.argv[1]

g = Genesis(seed=42).boot()
health = g.health()

assert "kernel" in health["phases"]
assert "forge" in health["phases"], f"forge phase missing: {health['phases']}"
assert "cortex" in health["phases"]
assert health["subsystems"] >= 23, f"expected 23+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge", "forge"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

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

# Live cortex observed the traffic (including forge events)
from skeleton.cortex import live
status = live.status()
assert status["live"] and status["events_captured"] > 0
forge_events = live.get_live().recent_events("forge", n=5)
assert len(forge_events) > 0, "cortex saw no forge events"

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

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, forge wired, godot verified, 4 planes, jeeves={reply['provider']}, persistence OK)")
PY
