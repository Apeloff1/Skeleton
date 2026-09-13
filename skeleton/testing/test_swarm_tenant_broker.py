import pytest

from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_quota import Quota
from skeleton.agents.swarm_runtime import AdmissionError, SwarmTask, TaskState
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker


def _broker():
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w", capacity=4)
    ingress = SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100)
    tenant = TenantSwarmBroker(SwarmBroker(runtime), ingress)
    return runtime, ingress, tenant


def test_tenant_broker_tracks_lease_and_success() -> None:
    runtime, ingress, broker = _broker()
    result = broker.submit_and_dispatch("acme", SwarmTask("task", {"x": 1}))
    assert result.admitted is True and result.leased is True
    assert ingress.phase("acme", "task") == "leased"

    completion = broker.record_success("w", "task", completion_token="done-1")
    assert completion.task.state is TaskState.SUCCEEDED
    assert broker.tenant_for("task") == "acme"
    assert ingress.phase("acme", "task") is None
    assert broker.status()["tracked_tasks"] == 0
    assert broker.status()["terminal_records"] == 1


def test_tenant_broker_failure_requeues_accounting() -> None:
    runtime, ingress, broker = _broker()
    broker.submit_and_dispatch("acme", SwarmTask("task", {}, max_attempts=2))
    failed = broker.record_failure("w", "task", "retry", completion_token="attempt-1")
    assert failed.task.state is TaskState.QUEUED
    assert ingress.phase("acme", "task") == "queued"
    assert broker.tenant_for("task") == "acme"


def test_tenant_broker_terminal_failure_releases_accounting() -> None:
    runtime, ingress, broker = _broker()
    broker.submit_and_dispatch("acme", SwarmTask("task", {}, max_attempts=1))
    failed = broker.record_failure("w", "task", "fatal", completion_token="attempt-1")
    assert failed.task.state is TaskState.DEAD
    assert broker.tenant_for("task") == "acme"
    assert ingress.phase("acme", "task") is None
    assert broker.status()["tracked_tasks"] == 0


def test_tenant_broker_rolls_back_ingress_when_runtime_rejects() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=1)
    runtime.submit(SwarmTask("occupied", {}))
    ingress = SwarmIngressGovernor()
    broker = TenantSwarmBroker(SwarmBroker(runtime), ingress)
    with pytest.raises(AdmissionError):
        broker.submit_and_dispatch("acme", SwarmTask("blocked", {}))
    assert broker.tenant_for("blocked") is None
    assert ingress.phase("acme", "blocked") is None


def test_tenant_broker_rejects_cross_tenant_task_collision() -> None:
    runtime, ingress, broker = _broker()
    broker.submit_and_dispatch("alpha", SwarmTask("task", {}))
    with pytest.raises(AdmissionError):
        broker.submit_and_dispatch("beta", SwarmTask("task", {}))


def test_tenant_broker_enforces_tenant_queue_quota() -> None:
    runtime = HardenedSwarmRuntime()
    ingress = SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100)
    ingress.configure_tenant("acme", quota=Quota(max_queued=1, max_leased=1, max_payload_bytes=1000))
    broker = TenantSwarmBroker(SwarmBroker(runtime), ingress)

    first = broker.submit_and_dispatch("acme", SwarmTask("one", {}))
    second = broker.submit_and_dispatch("acme", SwarmTask("two", {}))
    assert first.admitted is True and first.leased is False
    assert second.admitted is False
    assert second.reason == "queued quota exceeded"


def test_duplicate_completion_token_is_idempotent_at_tenant_boundary() -> None:
    runtime, ingress, broker = _broker()
    broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    first = broker.record_success("w", "task", completion_token="same")
    second = broker.record_success("w", "task", completion_token="same")
    assert first.duplicate is False
    assert second.duplicate is True
    assert ingress.phase("acme", "task") is None
    assert broker.status()["terminal_records"] == 1
