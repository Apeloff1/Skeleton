import pytest

from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_runtime import AdmissionError, SwarmTask, TaskState
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker


def _terminalized_broker() -> tuple[HardenedSwarmRuntime, SwarmIngressGovernor, TenantSwarmBroker]:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w", capacity=1)
    ingress = SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100)
    broker = TenantSwarmBroker(SwarmBroker(runtime), ingress)
    broker.submit_and_dispatch("acme", SwarmTask("task", {}, max_attempts=1))
    broker.record_failure("w", "task", "fatal", completion_token="terminal")
    assert runtime.task("task").state is TaskState.DEAD
    assert broker.tenant_for("task") == "acme"
    return runtime, ingress, broker


def test_revived_terminal_task_resubmission_requires_repair() -> None:
    runtime, ingress, broker = _terminalized_broker()
    runtime.revive("task", reset_attempts=True)

    with pytest.raises(AdmissionError, match="terminal tenant task is active: task; repair required"):
        broker.submit_and_dispatch("acme", SwarmTask("task", {"replacement": True}))

    assert runtime.task("task").state is TaskState.QUEUED
    assert ingress.phase("acme", "task") is None
    assert broker.reconcile()["terminal_not_terminal"] == ("task",)


def test_repair_reactivates_revived_terminal_task_before_resubmission() -> None:
    runtime, ingress, broker = _terminalized_broker()
    runtime.revive("task", reset_attempts=True)

    repaired = broker.repair()
    duplicate = broker.submit_and_dispatch("acme", SwarmTask("task", {"replacement": True}))

    assert repaired.reactivated == 1
    assert repaired.restored_accounting == 1
    assert ingress.phase("acme", "task") == "queued"
    assert duplicate.admitted is True
    assert duplicate.duplicate is True
    assert duplicate.leased is False
    assert duplicate.reason == "active task already accounted in state queued"


def test_leased_revival_drift_also_requires_repair() -> None:
    runtime, ingress, broker = _terminalized_broker()
    runtime.revive("task", reset_attempts=True)
    leased = runtime.lease("w")
    assert leased and leased[0].state is TaskState.LEASED

    with pytest.raises(AdmissionError, match="repair required"):
        broker.submit_and_dispatch("acme", SwarmTask("task", {}))

    repaired = broker.repair()
    assert repaired.reactivated == 1
    assert repaired.restored_accounting == 1
    assert ingress.phase("acme", "task") == "leased"
