"""Runtime-control regressions for cancellation, deadlines, leases, and concurrency."""

from __future__ import annotations

import threading
import time

import pytest

from skeleton.shells.admission_lease import AdmissionLeaseConflict, AdmissionLeases
from skeleton.shells.cancellation import (
    CancellationError,
    CancellationReason,
    CancellationRegistry,
    CancellationToken,
)
from skeleton.shells.command_budget import CommandBudgetPolicy, CommandBudgets
from skeleton.shells.concurrency import ConcurrencyLimit, WeightedConcurrency
from skeleton.shells.deadlines import DeadlineClock, DeadlineExceeded, TimeBudget


def test_cancellation_token_initially_active():
    token = CancellationToken()
    assert not token.cancelled
    token.require_active()


def test_cancellation_token_cancel_once():
    token = CancellationToken()
    assert token.cancel(CancellationReason.USER)
    assert token.cancelled
    assert not token.cancel(CancellationReason.SHUTDOWN)


def test_cancellation_token_snapshot():
    now = [5.0]
    token = CancellationToken(clock=lambda: now[0])
    token.cancel(CancellationReason.POLICY, detail="denied")
    state = token.snapshot()
    assert state.cancelled
    assert state.reason is CancellationReason.POLICY
    assert state.detail == "denied"
    assert state.cancelled_at == 5.0


def test_cancellation_require_active_raises_after_cancel():
    token = CancellationToken()
    token.cancel(CancellationReason.USER)
    with pytest.raises(CancellationError):
        token.require_active()


def test_cancellation_wait_returns_true_after_cancel():
    token = CancellationToken()
    token.cancel()
    assert token.wait(0)


def test_cancellation_wait_rejects_negative_timeout():
    with pytest.raises(ValueError):
        CancellationToken().wait(-1)


def test_cancellation_detail_is_bounded():
    token = CancellationToken()
    with pytest.raises(ValueError):
        token.cancel(detail="x" * 513)


def test_cancellation_registry_create_get_require():
    registry = CancellationRegistry()
    token = registry.create("x")
    assert registry.get("x") is token
    assert registry.require("x") is token


def test_cancellation_registry_duplicate_key_rejected():
    registry = CancellationRegistry()
    registry.create("x")
    with pytest.raises(RuntimeError):
        registry.create("x")


def test_cancellation_registry_capacity():
    registry = CancellationRegistry(max_tokens=1)
    registry.create("x")
    with pytest.raises(RuntimeError):
        registry.create("y")


def test_cancellation_registry_cancel():
    registry = CancellationRegistry()
    registry.create("x")
    assert registry.cancel("x", CancellationReason.SHUTDOWN)
    assert registry.require("x").snapshot().reason is CancellationReason.SHUTDOWN


def test_cancellation_registry_remove_active_when_required_rejected():
    registry = CancellationRegistry()
    registry.create("x")
    with pytest.raises(RuntimeError):
        registry.remove("x", require_cancelled=True)


def test_cancellation_registry_remove_cancelled():
    registry = CancellationRegistry()
    registry.create("x")
    registry.cancel("x")
    assert registry.remove("x", require_cancelled=True)


def test_cancellation_registry_cancelled_keys_sorted():
    registry = CancellationRegistry()
    registry.create("b")
    registry.create("a")
    registry.cancel("b")
    registry.cancel("a")
    assert registry.cancelled() == ("a", "b")


def test_deadline_after_and_remaining():
    now = [10.0]
    clock = DeadlineClock(clock=lambda: now[0])
    deadline = clock.after(5)
    assert deadline.expires_at == 15
    assert clock.remaining(deadline) == 5


def test_deadline_exact_expiry():
    now = [10.0]
    clock = DeadlineClock(clock=lambda: now[0])
    deadline = clock.after(5)
    now[0] = 15
    assert clock.remaining(deadline) == 0
    with pytest.raises(DeadlineExceeded):
        clock.require(deadline)


def test_deadline_clamp_timeout():
    now = [0.0]
    clock = DeadlineClock(clock=lambda: now[0])
    deadline = clock.after(5)
    assert clock.clamp_timeout(deadline, 10) == 5
    assert clock.clamp_timeout(deadline, 2) == 2


def test_deadline_rejects_nonpositive_duration():
    with pytest.raises(ValueError):
        DeadlineClock().after(0)


def test_time_budget_reserve_and_record():
    now = [0.0]
    budget = TimeBudget(10, clock=lambda: now[0])
    assert budget.reserve(20) == 10
    snapshot = budget.record(3)
    assert snapshot.remaining_seconds == 7
    assert budget.require() == 7


def test_time_budget_exhaustion():
    budget = TimeBudget(1)
    budget.record(1)
    with pytest.raises(DeadlineExceeded):
        budget.require()


def test_time_budget_can_overrecord_but_reports_zero_remaining():
    budget = TimeBudget(1)
    snapshot = budget.record(5)
    assert snapshot.exhausted
    assert snapshot.remaining_seconds == 0


def test_weighted_concurrency_try_acquire_and_release():
    limiter = WeightedConcurrency(3)
    first = limiter.try_acquire(2, owner="a")
    assert first is not None
    assert limiter.snapshot().used == 2
    assert limiter.release(first)
    assert limiter.snapshot().used == 0


def test_weighted_concurrency_returns_none_when_full():
    limiter = WeightedConcurrency(2)
    first = limiter.try_acquire(2)
    assert first is not None
    assert limiter.try_acquire(1) is None


def test_weighted_concurrency_rejects_weight_over_capacity():
    limiter = WeightedConcurrency(2)
    with pytest.raises(ConcurrencyLimit):
        limiter.try_acquire(3)


def test_weighted_concurrency_stale_release_is_false():
    limiter = WeightedConcurrency(2)
    permit = limiter.try_acquire()
    assert limiter.release(permit)
    assert not limiter.release(permit)


def test_weighted_concurrency_require_stale_raises():
    limiter = WeightedConcurrency(2)
    permit = limiter.try_acquire()
    limiter.release(permit)
    with pytest.raises(ConcurrencyLimit):
        limiter.require(permit)


def test_weighted_concurrency_by_owner():
    limiter = WeightedConcurrency(3)
    a = limiter.try_acquire(1, owner="a")
    b = limiter.try_acquire(1, owner="b")
    c = limiter.try_acquire(1, owner="a")
    assert [item.permit_id for item in limiter.by_owner("a")] == [a.permit_id, c.permit_id]
    limiter.release(a)
    limiter.release(b)
    limiter.release(c)


def test_weighted_concurrency_blocking_acquire_times_out():
    limiter = WeightedConcurrency(1)
    permit = limiter.acquire()
    with pytest.raises(ConcurrencyLimit):
        limiter.acquire(timeout=0)
    limiter.release(permit)


def test_weighted_concurrency_waits_until_release():
    limiter = WeightedConcurrency(1)
    first = limiter.acquire()
    result = []

    def waiter():
        result.append(limiter.acquire(timeout=1))

    thread = threading.Thread(target=waiter)
    thread.start()
    time.sleep(0.02)
    limiter.release(first)
    thread.join(timeout=1)
    assert result
    limiter.release(result[0])


def test_admission_lease_acquire_require_release():
    now = [0.0]
    leases = AdmissionLeases(clock=lambda: now[0])
    lease = leases.acquire("k", principal="p", command="python", ttl_seconds=5)
    assert leases.require(lease) == lease
    assert leases.release(lease)
    with pytest.raises(AdmissionLeaseConflict):
        leases.require(lease)


def test_admission_lease_conflict():
    leases = AdmissionLeases()
    leases.acquire("k", principal="p", command="python")
    with pytest.raises(AdmissionLeaseConflict):
        leases.acquire("k", principal="p", command="python")


def test_admission_lease_expiry_allows_reacquire():
    now = [0.0]
    leases = AdmissionLeases(clock=lambda: now[0])
    first = leases.acquire("k", principal="p", command="python", ttl_seconds=5)
    now[0] = 5
    second = leases.acquire("k", principal="p", command="python")
    assert first.lease_id != second.lease_id


def test_admission_lease_renew_changes_revision():
    now = [0.0]
    leases = AdmissionLeases(clock=lambda: now[0])
    first = leases.acquire("k", principal="p", command="python", ttl_seconds=5)
    now[0] = 1
    second = leases.renew(first, ttl_seconds=10)
    assert second.revision == 2
    assert second.lease_id == first.lease_id
    assert second.expires_at == 11


def test_admission_lease_old_revision_cannot_release_new():
    now = [0.0]
    leases = AdmissionLeases(clock=lambda: now[0])
    first = leases.acquire("k", principal="p", command="python")
    second = leases.renew(first)
    assert not leases.release(first)
    assert leases.release(second)


def test_command_budget_initially_allowed():
    budgets = CommandBudgets()
    assert budgets.inspect("python").allowed


def test_command_budget_start_limit():
    budgets = CommandBudgets(CommandBudgetPolicy(max_starts=1))
    budgets.reserve_start("python")
    decision = budgets.inspect("python")
    assert not decision.allowed
    assert "start" in decision.reason


def test_command_budget_failure_limit():
    budgets = CommandBudgets(CommandBudgetPolicy(max_failures=1))
    budgets.record_result("python", ok=False, runtime_ms=0, output_bytes=0)
    assert not budgets.inspect("python").allowed


def test_command_budget_runtime_limit():
    budgets = CommandBudgets(CommandBudgetPolicy(max_runtime_ms=10))
    budgets.record_result("python", ok=True, runtime_ms=10, output_bytes=0)
    assert not budgets.inspect("python").allowed


def test_command_budget_output_limit():
    budgets = CommandBudgets(CommandBudgetPolicy(max_output_bytes=10))
    budgets.record_result("python", ok=True, runtime_ms=0, output_bytes=10)
    assert not budgets.inspect("python").allowed


def test_command_budget_window_reset():
    now = [0.0]
    budgets = CommandBudgets(
        CommandBudgetPolicy(max_starts=1, window_seconds=5),
        clock=lambda: now[0],
    )
    budgets.reserve_start("python")
    assert not budgets.inspect("python").allowed
    now[0] = 5
    assert budgets.inspect("python").allowed


def test_command_budget_per_command_override():
    budgets = CommandBudgets(CommandBudgetPolicy(max_starts=100))
    budgets.set_policy("python", CommandBudgetPolicy(max_starts=1))
    budgets.reserve_start("python")
    assert not budgets.inspect("python").allowed
    assert budgets.inspect("git").allowed


def test_command_budget_cardinality():
    budgets = CommandBudgets(max_commands=1)
    budgets.inspect("python")
    with pytest.raises(RuntimeError):
        budgets.inspect("git")
