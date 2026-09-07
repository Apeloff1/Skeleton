#!/usr/bin/env bash
# Smoke test the cockpit: boot genesis, hit health, verify handles,
# four-plane retrieval, and the Jeeves provider path.
set -euo pipefail

python - <<'PY'
from skeleton.genesis import Genesis

g = Genesis(seed=42).boot()
health = g.health()

assert "kernel" in health["phases"]
assert "cortex" in health["phases"]
assert health["subsystems"] >= 20, f"expected 20+ subsystems, got {health['subsystems']}"
assert health["invariant_violations"] == 0

required = ["lattice", "rag", "trinity", "orchestrator", "mesh", "fortress", "quad", "cortex", "ranker"]
for handle in required:
    assert handle in g.handles, f"missing handle: {handle}"

# Retrieval: vector RAG default + four quad planes
from skeleton.memory.vector import VectorStore
assert isinstance(g.get("rag"), VectorStore), "RAG plane should be VectorStore"
quad = g.get("quad")
assert set(quad._planes.keys()) == {"rag", "cag", "mag", "kag"}, f"quad planes: {quad._planes.keys()}"

# End-to-end retrieval
from skeleton.memory.core import Chunk
g.get("rag").add(Chunk(text="skeleton forge builds game blueprints", chunk_id="smoke-1"))
quad._planes["kag"].graph.add("forge", "produces", "blueprints")
results = quad.retrieve("forge blueprints", k=5)
assert len(results) > 0, "quad retrieval returned nothing"

# Jeeves provider path through API server state
from skeleton.api.server import ServerState
state = ServerState()
state.wire_from_genesis(g)
session = state.jeeves.open_session("smoke-user")
reply = state.jeeves.ask(session.session_id, "what does the forge build?")
assert "forge" in reply["content"].lower(), f"jeeves reply missing context: {reply}"
assert reply["provider"] in ("local-echo", "openai", "anthropic")

# Live cortex observed the traffic
from skeleton.cortex import live
status = live.status()
assert status["live"] and status["events_captured"] > 0

print(f"cockpit smoke: OK ({health['subsystems']} subsystems, 4 planes, jeeves={reply['provider']}, cortex={status['events_captured']} events)")
PY
