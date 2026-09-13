from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmTask
from skeleton.api.server import ServerState


def _state() -> ServerState:
    state = ServerState()
    state.bind_swarm_runtime(HardenedSwarmRuntime())
    state.bind_swarm_ingress(SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))
    state.swarm_recovery = SwarmRecoveryManager()
    return state


def test_health_is_ready_when_runtime_and_tenant_checkpoints_align() -> None:
    state = _state()
    state.swarm_recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    health = state.is_healthy()
    assert health["checks"]["swarm_recovery"]["tenant_aligned"] is True
    assert health["overall"] is True


def test_health_fails_when_tenant_checkpoint_lags_runtime() -> None:
    state = _state()
    state.swarm_recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    state.swarm.submit(SwarmTask("later", {}))
    state.swarm_recovery.checkpoint(state.swarm)

    health = state.is_healthy()

    assert health["checks"]["swarm_recovery"]["tenant_aligned"] is False
    assert health["overall"] is False


def test_runtime_only_history_without_any_sidecar_remains_ready() -> None:
    state = _state()
    state.swarm_recovery.checkpoint(state.swarm)
    health = state.is_healthy()
    assert health["checks"]["swarm_recovery"]["latest_tenant_sequence"] is None
    assert health["checks"]["swarm_recovery"]["tenant_aligned"] is True
    assert health["overall"] is True
