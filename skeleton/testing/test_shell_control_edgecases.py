"""Additional control-plane edge cases for budgets, leases, traces, and events."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.admission_lease import AdmissionLeaseConflict, AdmissionLeases
from skeleton.shells.cancellation import CancellationReason, CancellationRegistry
from skeleton.shells.command_budget import CommandBudgetPolicy, CommandBudgets
from skeleton.shells.concurrency import ConcurrencyLimit, WeightedConcurrency
from skeleton.shells.deadlines import Deadline, DeadlineClock, DeadlineExceeded, TimeBudget
from skeleton.shells.failure_ledger import ShellFailureKind, ShellFailureLedger
from skeleton.shells.shell_events import ShellEvent, ShellEvents
from skeleton.shells.tracing import ShellSpan, ShellTracer


def test_deadline_remaining_never_negative():
    deadline = Deadline(1)
    assert deadline.remaining(2) == 0


def test_deadline_expired_boundary():
    deadline = Deadline(1)
    assert not deadline.expired(0.999)
    assert deadline.expired(1)


def test_deadline_require_returns_remaining():
    now = [2.0]
    clock = DeadlineClock(clock=lambda: now[0])
    deadline = Deadline(5)
    assert clock.require(deadline) == 3


def test_deadline_clamp_rejects_nonpositive_requested():
    clock = DeadlineClock()
    with pytest.raises(ValueError):
        clock.clamp_timeout(Deadline(999999999), 0)


def test_time_budget_rejects_negative_record():
    with pytest.raises(ValueError):
        TimeBudget(1).record(-1)


def test_time_budget_reserve_rejects_nonpositive():
    with pytest.raises(ValueError):
        TimeBudget(1).reserve(0)


def test_concurrency_capacity_must_be_positive():
    with pytest.raises(ValueError):
        WeightedConcurrency(0)


def test_concurrency_weight_must_be_positive():
    with pytest.raises(ValueError):
        WeightedConcurrency(1).try_acquire(0)


def test_concurrency_owner_must_be_nonempty():
    with pytest.raises(ValueError):
        WeightedConcurrency(1).try_acquire(1, owner="")


def test_concurrency_snapshot_available():
    limiter = WeightedConcurrency(5)
    a = limiter.acquire(2)
    b = limiter.acquire(1)
    snap = limiter.snapshot()
    assert snap.capacity == 5
    assert snap.used == 3
    assert snap.available == 2
    assert snap.permits == 2
    limiter.release(a)
    limiter.release(b)


def test_lease_capacity():
    leases = AdmissionLeases(max_leases=1)
    leases.acquire("a", principal="p", command="python")
    with pytest.raises(AdmissionLeaseConflict):
        leases.acquire("b", principal="p", command="python")


def test_lease_expired_snapshot_pruned():
    now = [0.0]
    leases = AdmissionLeases(clock=lambda: now[0])
    leases.acquire("a", principal="p", command="python", ttl_seconds=1)
    now[0] = 1
    assert leases.snapshot() == ()


def test_lease_require_old_after_renew_rejected():
    leases = AdmissionLeases()
    first = leases.acquire("a", principal="p", command="python")
    second = leases.renew(first)
    with pytest.raises(AdmissionLeaseConflict):
        leases.require(first)
    assert leases.require(second) == second


def test_budget_result_metrics_accumulate():
    budgets = CommandBudgets()
    budgets.reserve_start("python")
    budgets.record_result("python", ok=True, runtime_ms=10, output_bytes=20)
    budgets.reserve_start("python")
    usage = budgets.record_result("python", ok=False, runtime_ms=5, output_bytes=3)
    assert usage.starts == 2
    assert usage.failures == 1
    assert usage.runtime_ms == 15
    assert usage.output_bytes == 23


def test_budget_retry_after_counts_down():
    now = [0.0]
    budgets = CommandBudgets(
        CommandBudgetPolicy(max_starts=1, window_seconds=10),
        clock=lambda: now[0],
    )
    budgets.reserve_start("python")
    now[0] = 3
    decision = budgets.inspect("python")
    assert not decision.allowed
    assert decision.retry_after_seconds == 7


def test_budget_snapshot_sorted():
    budgets = CommandBudgets()
    budgets.inspect("b")
    budgets.inspect("a")
    assert list(budgets.snapshot()) == ["a", "b"]


def test_events_query_after_sequence():
    events = ShellEvents()
    events.emit("a")
    second = events.emit("b")
    third = events.emit("c")
    assert events.query(after_sequence=1) == (second, third)


def test_events_query_command_filter():
    events = ShellEvents()
    events.emit("x", command="python")
    events.emit("x", command="git")
    assert [item.command for item in events.query(command="python")] == ["python"]


def test_events_data_is_copied():
    data = {"x": 1}
    event = ShellEvent(1, "x", 0, data=data)
    data["x"] = 2
    assert event.data["x"] == 1


def test_trace_attributes_are_copied():
    attrs = {"x": "1"}
    span = ShellSpan("s", "t", "", "name", 0, attributes=attrs)
    attrs["x"] = "2"
    assert span.attributes["x"] == "1"


def test_tracer_finish_error_type():
    tracer = ShellTracer()
    span = tracer.start("x", trace_id="t")
    finished = tracer.finish(span, error_type="RuntimeError")
    assert finished.error_type == "RuntimeError"


def test_tracer_trace_filters_id():
    tracer = ShellTracer()
    a = tracer.start("a", trace_id="t1")
    b = tracer.start("b", trace_id="t2")
    assert tracer.trace("t1") == (a,)
    assert tracer.trace("t2") == (b,)


def test_failure_query_after_sequence():
    ledger = ShellFailureLedger()
    first = ledger.record("a", ShellFailureKind.INTERNAL)
    second = ledger.record("b", ShellFailureKind.TIMEOUT)
    assert ledger.query(after_sequence=first.sequence) == (second,)


def test_failure_detail_bound():
    ledger = ShellFailureLedger()
    with pytest.raises(ValueError):
        ledger.record("a", ShellFailureKind.INTERNAL, detail="x" * 513)


def test_cancellation_registry_snapshot_sorted():
    registry = CancellationRegistry()
    registry.create("b")
    registry.create("a")
    assert list(registry.snapshot()) == ["a", "b"]


def test_cancellation_reason_preserved():
    registry = CancellationRegistry()
    registry.create("x")
    registry.cancel("x", CancellationReason.SUPERSEDED, detail="new plan")
    state = registry.snapshot()["x"]
    assert state.reason is CancellationReason.SUPERSEDED
    assert state.detail == "new plan"
