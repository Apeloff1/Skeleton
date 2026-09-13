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


def test_tokenless_success_callback_is_idempotent_after_terminalization() -> None:
    runtime, ingress, broker = _broker()
    broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    first = broker.record_success("w", "task")
    second = broker.record_success("w", "task")
    assert first.duplicate is False
    assert second.duplicate is True
    assert second.task.state is TaskState.SUCCEEDED
    assert runtime.task("task").state is TaskState.SUCCEEDED
    assert ingress.phase("acme", "task") is None


def test_tokenless_failure_callback_is_idempotent_after_terminalization() -> None:
    runtime, ingress, broker = _broker()
    broker.submit_and_dispatch("acme", SwarmTask("task", {}, max_attempts=1))
    first = broker.record_failure("w", "task", "fatal")
    second = broker.record_failure("w", "task", "duplicate fatal")
    assert first.duplicate is False
    assert second.duplicate is True
    assert second.task.state is TaskState.DEAD
    assert runtime.task("task").state is TaskState.DEAD
    assert ingress.phase("acme", "task") is None


def test_active_leased_task_resubmission_is_identity_idempotent() -> None:
    runtime, ingress, broker = _broker()
    first = broker.submit_and_dispatch("acme", SwarmTask("task", {"version": 1}))
    resident = runtime.task("task")
    duplicate = broker.submit_and_dispatch("acme", SwarmTask("task", {"version": 2}))

    assert first.leased is True
    assert duplicate.admitted is True
    assert duplicate.duplicate is True
    assert duplicate.leased is True
    assert duplicate.worker_id == "w"
    assert duplicate.reason == "active task already accounted in state leased"
    assert runtime.task("task") == resident
    assert ingress.phase("acme", "task") == "leased"


def test_active_queued_task_resubmission_is_identity_idempotent() -> None:
    runtime = HardenedSwarmRuntime()
    ingress = SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100)
    broker = TenantSwarmBroker(SwarmBroker(runtime), ingress)
    first = broker.submit_and_dispatch("acme", SwarmTask("task", {"version": 1}))
    resident = runtime.task("task")
    duplicate = broker.submit_and_dispatch("acme", SwarmTask("task", {"version": 2}))

    assert first.leased is False
    assert duplicate.duplicate is True
    assert duplicate.leased is False
    assert duplicate.worker_id is None
    assert duplicate.reason == "active task already accounted in state queued"
    assert runtime.task("task") == resident
    assert ingress.phase("acme", "task") == "queued"


def test_active_accounting_without_runtime_task_fails_closed() -> None:
    runtime, ingress, broker = _broker()
    broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    broker.rebind(SwarmBroker(HardenedSwarmRuntime()))

    with pytest.raises(AdmissionError, match="repair required"):
        broker.submit_and_dispatch("acme", SwarmTask("task", {}))


def test_terminal_task_resubmission_is_stable_duplicate_without_runtime_mutation() -> None:
    runtime, ingress, broker = _broker()
    broker.submit_and_dispatch("acme", SwarmTask("task", {"version": 1}))
    broker.record_success("w", "task", completion_token="done")
    resident = runtime.task("task")
    assert resident is not None and resident.state is TaskState.SUCCEEDED
    duplicate = broker.submit_and_dispatch("acme", SwarmTask("task", {"version": 2}))
    assert duplicate.admitted is True
    assert duplicate.duplicate is True
    assert duplicate.leased is False
    assert duplicate.worker_id is None
    assert duplicate.reason == "terminal task already accounted"
    assert runtime.task("task") == resident
    assert ingress.phase("acme", "task") is None


def test_terminal_task_resubmission_preserves_cross_tenant_ownership() -> None:
    runtime, ingress, broker = _broker()
    broker.submit_and_dispatch("alpha", SwarmTask("task", {}))
    broker.record_success("w", "task", completion_token="done")
    with pytest.raises(AdmissionError, match="task already belongs to tenant: alpha"):
        broker.submit_and_dispatch("beta", SwarmTask("task", {}))
    assert runtime.task("task").state is TaskState.SUCCEEDED
    assert ingress.phase("alpha", "task") is None


def test_terminal_record_retention_is_bounded_and_duplicate_refreshes_lru() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w", capacity=3)
    ingress = SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100)
    broker = TenantSwarmBroker(SwarmBroker(runtime), ingress, max_terminal_records=2)

    for task_id in ("one", "two"):
        broker.submit_and_dispatch("acme", SwarmTask(task_id, {}))
        broker.record_success("w", task_id, completion_token=f"done-{task_id}")

    refreshed = broker.submit_and_dispatch("acme", SwarmTask("one", {"duplicate": True}))
    assert refreshed.duplicate is True
    broker.submit_and_dispatch("acme", SwarmTask("three", {}))
    broker.record_success("w", "three", completion_token="done-three")
    status = broker.status()
    assert status["terminal_records"] == 2
    assert broker.tenant_for("one") == "acme"
    assert broker.tenant_for("two") is None
    assert broker.tenant_for("three") == "acme"
