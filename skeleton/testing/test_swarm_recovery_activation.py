import pytest

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmTask
from skeleton.api.server import ServerState
from skeleton.api.swarm_recovery_service import activate_recovery


def _state() -> ServerState:
    state = ServerState()
    state.bind_swarm_runtime(HardenedSwarmRuntime())
    state.bind_swarm_ingress(SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))
    state.swarm_recovery = SwarmRecoveryManager(max_checkpoints=4)
    return state


def test_activation_restores_selected_runtime_and_tenant_sidecar() -> None:
    state = _state()
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("first", {}))
    seq1 = state.swarm_recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("second", {}))
    seq2 = state.swarm_recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    assert (seq1, seq2) == (1, 2)

    result = activate_recovery(state, state.swarm_recovery, 1)

    assert result.sequence == 1
    assert result.tenant_source == "checkpoint"
    assert state.swarm.task("first") is not None
    assert state.swarm.task("second") is None
    assert state.swarm_tenant_broker.tenant_for("first") == "acme"
    assert state.swarm_tenant_broker.tenant_for("second") is None


def test_activation_uses_live_metadata_when_selected_checkpoint_has_no_sidecar() -> None:
    state = _state()
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    state.swarm_recovery.checkpoint(state.swarm)

    result = activate_recovery(state, state.swarm_recovery, 1)

    assert result.tenant_source == "live"
    assert state.swarm_tenant_broker.tenant_for("task") == "acme"
    assert state.swarm_ingress.status()["accounted_tasks"] == 1


def test_activation_rejects_live_metadata_newer_than_selected_runtime_atomically() -> None:
    state = _state()
    state.swarm_recovery.checkpoint(state.swarm)
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("later", {}))

    old_runtime = state.swarm
    old_broker = state.swarm_broker
    old_ingress = state.swarm_ingress
    old_tenant = state.swarm_tenant_broker

    with pytest.raises(ValueError, match="missing from restored runtime"):
        activate_recovery(state, state.swarm_recovery, 1)

    assert state.swarm is old_runtime
    assert state.swarm_broker is old_broker
    assert state.swarm_ingress is old_ingress
    assert state.swarm_tenant_broker is old_tenant
    assert state.swarm_tenant_broker.tenant_for("later") == "acme"


def test_activation_rejects_missing_checkpoint_without_mutation() -> None:
    state = _state()
    old_runtime = state.swarm
    with pytest.raises(KeyError, match="checkpoint not found"):
        activate_recovery(state, state.swarm_recovery, 99)
    assert state.swarm is old_runtime
