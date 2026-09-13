from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmTask
from skeleton.api.server import ServerState


def test_server_health_fails_when_swarm_is_critical() -> None:
    state = ServerState()
    state.swarm = HardenedSwarmRuntime()
    state.swarm.submit(SwarmTask("queued", {}))
    health = state.is_healthy()
    assert health["checks"]["swarm"]["status"] == "critical"
    assert health["overall"] is False


def test_server_health_remains_healthy_with_available_worker() -> None:
    state = ServerState()
    state.swarm = HardenedSwarmRuntime()
    state.swarm.register_worker("w")
    state.swarm.submit(SwarmTask("queued", {}))
    health = state.is_healthy()
    assert health["checks"]["swarm"]["status"] == "healthy"
    assert health["overall"] is True
