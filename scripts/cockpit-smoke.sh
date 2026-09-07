#!/usr/bin/env bash
# Smoke test the cockpit: boot genesis, hit health, verify handles,
# four-plane retrieval with self-populating KAG, Jeeves provider path,
# memory matrices, and the swarm-agents bridge.
set -euo pipefail

python - <<'PY'
from skeleton.genesis import Genesis

g = Genesis(seed=42).boot()
health = g.health()

assert "kernel" in health["phases"]
assert "cortex" in health["phases"]
assert health["subsystems"] >= 22, f"expected 22+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress",
            "quad", "cortex", "ranker", "coordinator", "bridge"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

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

# Live cortex observed the traffic
from skeleton.cortex import live
status = live.status()
assert status["live"] and status["events_captured"] > 0

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 4 planes, kag={kag.graph.stats()['triples']} triples, jeeves={reply['provider']}, matrices live)")
PY
