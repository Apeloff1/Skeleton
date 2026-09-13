import pytest
from fastapi import HTTPException

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_quota import Quota
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


def test_paired_restore_swaps_complete_bundle_and_preserves_ingress_policy(monkeypatch) -> None:
    state = _state()
    state.swarm_ingress.configure_tenant(
        "acme",
        quota=Quota(max_queued=7, max_leased=3, max_payload_bytes=700),
        weight=5,
    )
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {"x": 1}))
    recovery = SwarmRecoveryManager()
    recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    monkeypatch.setattr(routes, "_state", lambda: state)

    old_runtime = state.swarm
    old_broker = state.swarm_broker
    old_ingress = state.swarm_ingress
    old_tenant = state.swarm_tenant_broker

    result = routes.restore_latest(recovery=recovery)

    assert result["restored"] is True
    assert state.swarm is not old_runtime
    assert state.swarm_broker is not old_broker
    assert state.swarm_ingress is not old_ingress
    assert state.swarm_tenant_broker is not old_tenant
    assert state.swarm_broker.runtime is state.swarm
    assert state.swarm_tenant_broker.broker is state.swarm_broker
    assert state.swarm_tenant_broker.ingress is state.swarm_ingress
    assert state.swarm_ingress.quota.limit("acme") == Quota(max_queued=7, max_leased=3, max_payload_bytes=700)
    assert state.swarm_ingress.fairness.snapshot()["acme"]["weight"] == 5
    assert state.swarm_ingress.status()["accounted_tasks"] == 1


def test_paired_restore_failure_leaves_live_bundle_untouched(monkeypatch) -> None:
    state = _state()
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    recovery = SwarmRecoveryManager()
    recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    monkeypatch.setattr(routes, "_state", lambda: state)

    old_runtime = state.swarm
    old_broker = state.swarm_broker
    old_ingress = state.swarm_ingress
    old_tenant = state.swarm_tenant_broker

    def fail_restore(*args, **kwargs):
        raise ValueError("synthetic sidecar corruption")

    monkeypatch.setattr(recovery, "restore_tenants", fail_restore)

    with pytest.raises(HTTPException) as exc:
        routes.restore_latest(recovery=recovery)

    assert exc.value.status_code == 409
    assert state.swarm is old_runtime
    assert state.swarm_broker is old_broker
    assert state.swarm_ingress is old_ingress
    assert state.swarm_tenant_broker is old_tenant
    assert state.swarm_tenant_broker.tenant_for("task") == "acme"


def test_server_rejects_incoherent_staged_bundle() -> None:
    state = _state()
    other_runtime = HardenedSwarmRuntime()
    with pytest.raises(ValueError, match="runtime mismatch"):
        state.commit_swarm_bundle(other_runtime, state.swarm_broker, state.swarm_ingress, state.swarm_tenant_broker)
