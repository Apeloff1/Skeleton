import pytest

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import AdmissionError, SwarmTask
from skeleton.api import swarm_operator_routes as routes
from skeleton.api.server import ServerState


def _state() -> ServerState:
    state = ServerState()
    state.bind_swarm_runtime(HardenedSwarmRuntime())
    state.bind_swarm_ingress(SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))
    state.swarm_recovery = SwarmRecoveryManager(max_checkpoints=4)
    return state


def test_operator_restore_retires_old_tenant_generation(monkeypatch) -> None:
    state = _state()
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    recovery = SwarmRecoveryManager()
    recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    old = state.swarm_tenant_broker
    monkeypatch.setattr(routes, "_state", lambda: state)

    result = routes.restore_latest(recovery=recovery)

    assert result["restored"] is True
    assert old.is_retired() is True
    assert state.swarm_tenant_broker is not old
    assert state.swarm_tenant_broker.is_retired() is False
    with pytest.raises(AdmissionError, match="generation retired"):
        old.submit_and_dispatch("acme", SwarmTask("late", {}))


def test_operator_gc_retires_old_tenant_generation(monkeypatch) -> None:
    state = _state()
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    old = state.swarm_tenant_broker
    monkeypatch.setattr(routes, "_state", lambda: state)

    result = routes.gc(keep_terminal=0, runtime=state.swarm)

    assert result["tenant_repair"] is not None
    assert old.is_retired() is True
    assert state.swarm_tenant_broker is not old
    with pytest.raises(AdmissionError, match="generation retired"):
        old.submit_and_dispatch("acme", SwarmTask("late", {}))


def test_operator_restore_failure_does_not_retire_live_generation(monkeypatch) -> None:
    state = _state()
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    recovery = SwarmRecoveryManager()
    recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    old = state.swarm_tenant_broker
    monkeypatch.setattr(routes, "_state", lambda: state)
    monkeypatch.setattr(recovery, "restore_tenants", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("corrupt")))

    with pytest.raises(Exception):
        routes.restore_latest(recovery=recovery)

    assert state.swarm_tenant_broker is old
    assert old.is_retired() is False
