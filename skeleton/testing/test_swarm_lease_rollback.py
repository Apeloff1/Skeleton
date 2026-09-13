import math

import pytest

from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_exact_lease import lease_exact
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_lease_rollback import rollback_exact_lease
from skeleton.agents.swarm_quota import Quota
from skeleton.agents.swarm_runtime import LeaseError, SwarmRuntime, SwarmTask, TaskState
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


def test_exact_lease_clock_failure_does_not_partially_commit() -> None:
    runtime = SwarmRuntime(clock=lambda: 10.0)
    worker = runtime.register_worker("w")
    runtime.submit(SwarmTask("task", {}))
    before_events = runtime.events()

    def broken_clock() -> float:
        raise RuntimeError("clock unavailable")

    runtime._clock = broken_clock
    with pytest.raises(RuntimeError, match="clock unavailable"):
        lease_exact(runtime, "w", "task")

    resident = runtime.task("task")
    assert resident is not None and resident.state is TaskState.QUEUED
    assert resident.attempts == 0
    assert worker.active == set()
    assert worker.accepted == 0
    assert runtime.events() == before_events


def test_exact_lease_commit_uses_one_clock_sample() -> None:
    runtime = SwarmRuntime(clock=lambda: 1.0)
    worker = runtime.register_worker("w")
    runtime.submit(SwarmTask("task", {}))
    calls = 0

    def single_sample_clock() -> float:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("clock sampled twice")
        return 42.0

    runtime._clock = single_sample_clock
    leased = lease_exact(runtime, "w", "task")

    assert calls == 1
    assert leased.state is TaskState.LEASED
    assert leased.attempts == 1
    assert leased.lease_deadline == 72.0
    assert worker.last_seen == 42.0
    assert worker.active == {"task"}
    assert worker.accepted == 1
    assert runtime.events()[-1] == (42.0, "task.leased", "task")


def test_exact_lease_rollback_clock_failure_does_not_partially_commit() -> None:
    runtime = SwarmRuntime(clock=lambda: 10.0)
    worker = runtime.register_worker("w")
    runtime.submit(SwarmTask("task", {}))
    leased = lease_exact(runtime, "w", "task")
    before_events = runtime.events()

    def broken_clock() -> float:
        raise RuntimeError("clock unavailable")

    runtime._clock = broken_clock
    with pytest.raises(RuntimeError, match="clock unavailable"):
        rollback_exact_lease(runtime, "w", "task")

    assert runtime.task("task") == leased
    assert worker.active == {"task"}
    assert worker.accepted == 1
    assert runtime.snapshot().leased == 1
    assert runtime.snapshot().queued == 0
    assert runtime.events() == before_events


def test_exact_lease_rollback_commit_uses_one_clock_sample() -> None:
    runtime = SwarmRuntime(clock=lambda: 1.0)
    worker = runtime.register_worker("w")
    runtime.submit(SwarmTask("task", {}))
    lease_exact(runtime, "w", "task")
    calls = 0

    def single_sample_clock() -> float:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("clock sampled twice")
        return 84.0

    runtime._clock = single_sample_clock
    restored = rollback_exact_lease(runtime, "w", "task")

    assert calls == 1
    assert restored.state is TaskState.QUEUED
    assert restored.attempts == 0
    assert restored.leased_to is None
    assert restored.lease_deadline is None
    assert worker.active == set()
    assert worker.accepted == 0
    assert runtime.snapshot().queued == 1
    assert runtime.snapshot().leased == 0
    assert runtime.events()[-1] == (84.0, "task.lease_rolled_back", "task")


@pytest.mark.parametrize("clock_value", [math.nan, math.inf, -math.inf])
def test_exact_lease_rejects_non_finite_clock_without_mutation(clock_value: float) -> None:
    runtime = SwarmRuntime(clock=lambda: 1.0)
    worker = runtime.register_worker("w")
    runtime.submit(SwarmTask("task", {}))
    before_events = runtime.events()
    runtime._clock = lambda: clock_value

    with pytest.raises(LeaseError, match="clock must be a finite number"):
        lease_exact(runtime, "w", "task")

    task = runtime.task("task")
    assert task is not None and task.state is TaskState.QUEUED and task.attempts == 0
    assert worker.active == set()
    assert worker.accepted == 0
    assert runtime.events() == before_events


@pytest.mark.parametrize("lease_seconds", [math.nan, math.inf, -math.inf, 0.0, -1.0, True])
def test_exact_lease_rejects_invalid_default_duration_without_mutation(lease_seconds: object) -> None:
    runtime = SwarmRuntime(clock=lambda: 5.0)
    worker = runtime.register_worker("w")
    runtime.submit(SwarmTask("task", {}))
    before_events = runtime.events()
    runtime.default_lease_seconds = lease_seconds

    with pytest.raises(LeaseError, match="default_lease_seconds"):
        lease_exact(runtime, "w", "task")

    task = runtime.task("task")
    assert task is not None and task.state is TaskState.QUEUED and task.attempts == 0
    assert worker.active == set()
    assert worker.accepted == 0
    assert runtime.events() == before_events


def test_exact_lease_rejects_non_string_identifiers_before_lookup() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    runtime.submit(SwarmTask("task", {}))

    with pytest.raises(LeaseError, match="worker_id must be a string"):
        lease_exact(runtime, 7, "task")
    with pytest.raises(LeaseError, match="task_id must be a string"):
        lease_exact(runtime, "w", None)
