import pytest

from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_runtime import AdmissionError, SwarmTask
from skeleton.agents.swarm_supervisor import SwarmSupervisor
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker
from skeleton.api.server import ServerState


def _state() -> ServerState:
    state = ServerState()
    state.bind_swarm_runtime(HardenedSwarmRuntime())
    state.bind_swarm_ingress(SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))
    return state


def test_commit_bundle_rejects_supervisor_generation_mismatch() -> None:
    state = _state()
    runtime = HardenedSwarmRuntime()
    ingress = state.swarm_ingress.fork_empty()
    broker = SwarmBroker(runtime, supervisor=SwarmSupervisor())
    tenant = TenantSwarmBroker(broker, ingress)

    with pytest.raises(ValueError, match="supervisor mismatch"):
        state.commit_swarm_bundle(runtime, broker, ingress, tenant)


def test_commit_bundle_rejects_unreconciled_tenant_metadata() -> None:
    state = _state()
    runtime = HardenedSwarmRuntime()
    ingress = state.swarm_ingress.fork_empty()
    broker = SwarmBroker(runtime, supervisor=state.swarm_supervisor)
    tenant = TenantSwarmBroker(broker, ingress)
    tenant._tenant_by_task["ghost"] = "acme"

    with pytest.raises(ValueError, match="not reconciled"):
        state.commit_swarm_bundle(runtime, broker, ingress, tenant)


def test_commit_bundle_publishes_coherent_reconciled_generation() -> None:
    state = _state()
    previous = state.swarm_tenant_broker
    runtime = HardenedSwarmRuntime()
    runtime.submit(SwarmTask("task", {}))
    ingress = state.swarm_ingress.fork_empty()
    broker = SwarmBroker(runtime, supervisor=state.swarm_supervisor)
    tenant = TenantSwarmBroker(broker, ingress)
    tenant._tenant_by_task["task"] = "acme"
    tenant.repair()

    state.commit_swarm_bundle(runtime, broker, ingress, tenant)

    assert state.swarm is runtime
    assert state.swarm_broker is broker
    assert state.swarm_ingress is ingress
    assert state.swarm_tenant_broker is tenant
    assert previous.is_retired() is True
    assert tenant.is_retired() is False
    assert tenant.reconcile() == {
        "missing_active": (),
        "terminal_not_terminal": (),
        "active_terminal": (),
        "phase_mismatch": (),
    }
    assert ingress.phase("acme", "task") == "queued"


def test_retired_tenant_generation_rejects_late_mutations() -> None:
    state = _state()
    old = state.swarm_tenant_broker
    runtime = HardenedSwarmRuntime()
    ingress = state.swarm_ingress.fork_empty()
    broker = SwarmBroker(runtime, supervisor=state.swarm_supervisor)
    tenant = TenantSwarmBroker(broker, ingress)

    state.commit_swarm_bundle(runtime, broker, ingress, tenant)

    with pytest.raises(AdmissionError, match="generation retired"):
        old.submit_and_dispatch("acme", SwarmTask("late", {}))
    with pytest.raises(AdmissionError, match="generation retired"):
        old.repair()
    with pytest.raises(AdmissionError, match="generation retired"):
        old.rebind(broker)

    accepted = tenant.submit_and_dispatch("acme", SwarmTask("live", {}))
    assert accepted.admitted is True
    assert state.is_healthy()["overall"] is True
