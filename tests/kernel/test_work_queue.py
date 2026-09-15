"""Regression tests for the kernel work queue invariants."""

from __future__ import annotations

import pytest

from skeleton.kernel.work_queue import CompletionError, WorkQueue


def test_live_work_never_leaks_false_empty_result() -> None:
    queue = WorkQueue()
    queue.add_lane("interactive")
    queue.add_lane("background")
    queue.enqueue("interactive", "turn-1")
    queue.enqueue("background", "sweep-1")

    assert queue.dequeue() is not None


def test_weighted_fairness_converges_without_external_credit_polls() -> None:
    queue = WorkQueue(max_in_flight=1)
    queue.add_lane("background", weight=1.0, capacity=64)
    queue.add_lane("interactive", weight=3.0, capacity=64)
    for index in range(40):
        queue.enqueue("background", f"background-{index}")
        queue.enqueue("interactive", f"interactive-{index}")

    served = {"background": 0, "interactive": 0}
    for _ in range(20):
        result = queue.dequeue()
        assert result is not None
        lane, item = result
        served[lane] += 1
        queue.complete(lane, item)

    assert served == {"background": 5, "interactive": 15}


def test_expired_backlog_is_retired_iteratively() -> None:
    queue = WorkQueue(clock=lambda: 100.0)
    queue.add_lane("maintenance", capacity=1_500)
    for index in range(1_200):
        queue.enqueue("maintenance", f"expired-{index}", deadline=99.0)

    assert queue.dequeue() is None
    assert queue.depth() == 0
    assert queue.stats()["expired"] == 1_200


def test_completion_is_owned_by_exact_lane_and_item() -> None:
    queue = WorkQueue(max_in_flight=1)
    queue.add_lane("interactive")
    queue.enqueue("interactive", "turn-1")

    result = queue.dequeue()
    assert result is not None
    lane, item = result

    with pytest.raises(CompletionError):
        queue.complete("background", item)

    assert queue.stats()["in_flight"] == 1
    queue.complete(lane, item)
    assert queue.stats()["in_flight"] == 0

    with pytest.raises(CompletionError):
        queue.complete(lane, item)

    assert queue.stats()["in_flight"] == 0
    assert queue.stats()["completion_errors"] == 2


def test_invalid_completion_cannot_reopen_capacity() -> None:
    queue = WorkQueue(max_in_flight=1)
    queue.add_lane("interactive")
    queue.enqueue("interactive", "turn-1")
    queue.enqueue("interactive", "turn-2")

    first = queue.dequeue()
    assert first is not None
    lane, item = first
    assert queue.dequeue() is None

    with pytest.raises(CompletionError):
        queue.complete("wrong-lane", item)

    assert queue.dequeue() is None
    queue.complete(lane, item)

    second = queue.dequeue()
    assert second is not None
    assert second[1].item_id == "turn-2"


def test_submitter_ledger_drops_zero_count_entries() -> None:
    queue = WorkQueue(per_submitter_cap=1)
    queue.add_lane("interactive")
    queue.enqueue("interactive", "turn-1", submitter="producer-a")

    result = queue.dequeue()
    assert result is not None
    lane, item = result

    assert queue.stats()["submitters"] == {}
    queue.complete(lane, item)
