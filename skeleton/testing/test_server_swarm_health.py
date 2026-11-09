from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmRuntime
from skeleton.api.server import ServerState


def test_server_health_includes_swarm_and_recovery() -> None:
    state = ServerState()
    state.swarm = SwarmRuntime()
    state.swarm_recovery = SwarmRecoveryManager()
    health = state.is_healthy()
    assert health["overall"] is True
    assert health["checks"]["swarm"]["status"] == "healthy"
    assert health["checks"]["swarm_recovery"]["checkpoints"] == 0
