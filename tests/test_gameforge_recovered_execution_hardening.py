"""Adversarial execution-contract tests for the recovered Frontier primitives."""
from concurrent.futures import ThreadPoolExecutor
import pytest

from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_event_bus import EventEnvelope
from skeleton.frontier.gameforge_execution_fence_v2 import ExecutionFenceV2
from skeleton.frontier.gameforge_health_score import HealthScore
from skeleton.frontier.gameforge_lease import LeaseSet
from skeleton.frontier.gameforge_quorum import quorum, reached
from skeleton.frontier.gameforge_replay import ReplayCursor
from skeleton.frontier.gameforge_reservation_book import ReservationBook
from skeleton.frontier.gameforge_retry_budget import RetryBudget
from skeleton.frontier.gameforge_router import HealthRouter
from skeleton.frontier.gameforge_saga import Saga, SagaState
from skeleton.frontier.gameforge_scheduler import Scheduler


def test_replay_rejects_gap_and_reordering_without_advancing():
    cursor = ReplayCursor()
    with pytest.raises(ValueError, match="gap"):
        cursor.consume([EventEnvelope(0, "first"), EventEnvelope(2, "gap")])
    assert cursor.checkpoint == -1
    with pytest.raises(ValueError):
        cursor.consume([EventEnvelope(0, "first"), EventEnvelope(0, "duplicate")])
    assert cursor.checkpoint == -1
    assert len(cursor.consume([EventEnvelope(0, "first")])) == 1
    assert cursor.consume([EventEnvelope(0, "first")]) == ()


def test_fence_has_exactly_one_concurrent_winner():
    fence = ExecutionFenceV2()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: fence.acquire(), range(128)))
    assert sum(results) == 1 and fence.closed


def test_reservations_converge_and_stale_release_cannot_remove_new_generation():
    book = ReservationBook(1)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: book.add("same"), range(64)))
    assert all(item is results[0] for item in results)
    old = book.remove("same")
    new = book.add("same")
    assert book.remove_exact("same", old.sequence) is None
    assert book.remove_exact("same", new.sequence) == new


def test_duplicate_live_lease_is_not_admitted():
    leases = LeaseSet(32)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: leases.acquire("same"), range(64)))
    winners = [item for item in results if item is not None]
    assert len(winners) == leases.active == 1
    winners[0].release()
    assert leases.active == 0
    assert leases.acquire("same") is not None


def test_scheduler_does_not_expand_large_weight():
    scheduler = Scheduler({"a": 1, "b": 100_000_000})
    assert scheduler.size == 100_000_001
    assert [scheduler.next() for _ in range(4)] == ["a", "b", "b", "b"]
    scheduler.reset()
    assert scheduler.next() == "a"


@pytest.mark.parametrize("weights", [{"a": True}, {"a": 1 << 31}, {"": 1}])
def test_scheduler_rejects_unsafe_weights(weights):
    with pytest.raises(ValueError):
        Scheduler(weights)


def test_strict_health_and_dependency_expire():
    now = [10.0]
    router = HealthRouter(["a"], require_probe=True, ttl_seconds=5, clock=lambda: now[0])
    gate = DependencyGate(["a"], ttl_seconds=5, clock=lambda: now[0])
    assert router.next() is None and not gate.ready
    router.mark("a", True)
    gate.mark("a")
    assert router.next() == "a" and gate.ready
    now[0] = 15.0
    assert router.next() is None and not gate.ready
    now[0] = 9.0
    assert router.next() is None and not gate.ready


def test_health_requires_explicit_samples_in_strict_mode():
    score = HealthScore(minimum_samples=2)
    assert not score.healthy
    score.record(True)
    assert not score.healthy
    score.record(True)
    assert score.healthy


def test_retry_counters_are_not_publicly_rewriteable():
    budget = RetryBudget(3)
    with pytest.raises(AttributeError):
        budget.remaining = 999
    with ThreadPoolExecutor(max_workers=16) as pool:
        assert sum(pool.map(lambda _: budget.consume(), range(64))) == 3


def test_saga_state_cannot_bypass_transition_methods():
    saga = Saga()
    with pytest.raises(AttributeError):
        saga.state = SagaState.COMPENSATED
    saga.commit()
    saga.compensate()
    saga.finish_compensation()
    assert saga.state is SagaState.COMPENSATED


@pytest.mark.parametrize("total,votes", [(True, 1), (3, True), (3, 1.5)])
def test_quorum_rejects_noninteger_authority_counts(total, votes):
    with pytest.raises(ValueError):
        reached(total, votes)
    assert quorum(3) == 2
