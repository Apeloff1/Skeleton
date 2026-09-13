import pytest

from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_lease_rollback import rollback_exact_lease
from skeleton.agents.swarm_quota import Quota
from skeleton.agents.swarm_runtime import LeaseError, SwarmTask, TaskState
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker


def test_exact_lease_rollback_restores_prelease_runtime_counters() -> None:
    runtime = HardenedSwarmRuntime()
    worker = runtime.register_worker("w", capacity=1)
    runtime.submit(SwarmTask("task", {}))
    leased = runtime.lease("w", limit=1)[0]

    assert leased.state is TaskState.LEASED
    assert leased.attempts == 1
    assert worker.accepted == 1
    assert worker.active == {"task"}

    restored = rollback_exact_lease(runtime, "w", "task")

    assert restored.state is TaskState.QUEUED
    assert restored.attempts == 0
    assert restored.leased_to is None
    assert restored.lease_deadline is None
    assert worker.accepted == 0
    assert worker.active == set()
    assert runtime.snapshot().queued == 1
    assert runtime.snapshot().leased == 0
    assert runtime.events()[-1][1:] == ("task.lease_rolled_back", "task")


def test_exact_lease_rollback_rejects_wrong_owner_without_mutation() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("owner", capacity=1)
    runtime.register_worker("other", capacity=1)
    runtime.submit(SwarmTask("task", {}))
    leased = runtime.lease("owner", limit=1)[0]

    with pytest.raises(LeaseError, match="leased to owner"):
        rollback_exact_lease(runtime, "other", "task")

    assert runtime.task("task") == leased
    assert runtime.worker("owner").active == {"task"}
    assert runtime.worker("owner").accepted == 1


def test_tenant_broker_rolls_back_runtime_when_leased_quota_rejects() -> None:
    runtime = HardenedSwarmRuntime()
    worker = runtime.register_worker("w", capacity=2)
    ingress = SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100)
    ingress.configure_tenant(
        "acme",
        quota=Quota(max_queued=3, max_leased=1, max_payload_bytes=10_000),
    )
    broker = TenantSwarmBroker(SwarmBroker(runtime), ingress)

    first = broker.submit_and_dispatch("acme", SwarmTask("one", {}))
    second = broker.submit_and_dispatch("acme", SwarmTask("two", {}))

    assert first.leased is True
    assert second.admitted is True
    assert second.leased is False
    assert second.worker_id is None
    assert second.reason.startswith("lease accounting rejected: leased quota exceeded")

    one = runtime.task("one")
    two = runtime.task("two")
    assert one is not None and one.state is TaskState.LEASED and one.attempts == 1
    assert two is not None and two.state is TaskState.QUEUED and two.attempts == 0
    assert worker.active == {"one"}
    assert worker.accepted == 1

    assert ingress.phase("acme", "one") == "leased"
    assert ingress.phase("acme", "two") == "queued"
    usage = ingress.status()["quota"]["acme"]
    assert usage["leased"] == 1
    assert usage["queued"] == 1
    assert broker.reconcile() == {
        "missing_active": (),
        "terminal_not_terminal": (),
        "active_terminal": (),
        "phase_mismatch": (),
    }
