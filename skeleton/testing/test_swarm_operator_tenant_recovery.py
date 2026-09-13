from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmTask
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker
from skeleton.api import swarm_operator_routes as routes
from skeleton.api.server import ServerState


def _state() -> ServerState:
    state = ServerState()
    state.bind_swarm_runtime(HardenedSwarmRuntime())
    state.bind_swarm_ingress(SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))
    return state


def test_operator_checkpoint_captures_tenant_sidecar(monkeypatch) -> None:
    state = _state()
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {"x": 1}))
    recovery = SwarmRecoveryManager()
    monkeypatch.setattr(routes, "_state", lambda: state)

    result = routes.checkpoint(runtime=state.swarm, recovery=recovery)

    assert result["sequence"] == 1
    assert result["status"]["tenant_checkpoints"] == 1
    assert result["status"]["tenant_aligned"] is True


def test_operator_restore_rehydrates_empty_tenant_broker(monkeypatch) -> None:
    state = _state()
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {"x": 1}))
    recovery = SwarmRecoveryManager()
    recovery.checkpoint(state.swarm, state.swarm_tenant_broker)

    fresh_ingress = SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100)
    state.swarm_ingress = fresh_ingress
    state.swarm_tenant_broker = TenantSwarmBroker(state.swarm_broker, fresh_ingress)
    monkeypatch.setattr(routes, "_state", lambda: state)

    result = routes.restore_latest(recovery=recovery)

    assert result["restored"] is True
    assert result["tenant_repair"] is not None
    assert state.swarm_tenant_broker.tenant_for("task") == "acme"
    assert state.swarm_tenant_broker.ingress.phase("acme", "task") == "queued"


def test_operator_restore_repairs_live_metadata_without_double_accounting(monkeypatch) -> None:
    state = _state()
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    recovery = SwarmRecoveryManager()
    recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    monkeypatch.setattr(routes, "_state", lambda: state)

    before = state.swarm_ingress.status()["accounted_tasks"]
    result = routes.restore_latest(recovery=recovery)
    after = state.swarm_ingress.status()["accounted_tasks"]

    assert result["tenant_repair"] is not None
    assert before == 1
    assert after == 1
    assert state.swarm_tenant_broker.tenant_for("task") == "acme"


def test_operator_runtime_only_checkpoint_restores_without_tenant_sidecar(monkeypatch) -> None:
    state = _state()
    recovery = SwarmRecoveryManager()
    recovery.checkpoint(state.swarm)
    monkeypatch.setattr(routes, "_state", lambda: state)

    result = routes.restore_latest(recovery=recovery)

    assert result["restored"] is True
    assert result["status"]["tenant_checkpoints"] == 0
