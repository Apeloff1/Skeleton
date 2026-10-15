"""Regression coverage for recovery queue consumption and bounded admission."""

from __future__ import annotations

import pytest

from skeleton.app.runtime.reconciliation_queue import ReconciliationItem, ReconciliationQueue
from skeleton.app.runtime.recovery_worker import RecoveryWorker


def test_recovery_worker_consumes_fifo_items_without_attribute_errors():
    queue = ReconciliationQueue(max_items=3)
    queue.enqueue(ReconciliationItem("execution-a", "retry", 1))
    queue.enqueue(ReconciliationItem("execution-b", "reconcile", 2))
    worker = RecoveryWorker(queue)

    first = worker.process_next()
    second = worker.process_next()

    assert first is not None and first.processed and first.execution_id == "execution-a"
    assert second is not None and second.processed and second.execution_id == "execution-b"
    assert queue.size() == 0
    assert worker.process_next() is None


def test_recovery_queue_rejects_overflow_without_discarding_pending_work():
    queue = ReconciliationQueue(max_items=1)
    item = ReconciliationItem("execution-original", "pending", 1)
    queue.enqueue(item)

    with pytest.raises(OverflowError, match="reconciliation queue is full"):
        queue.enqueue(ReconciliationItem("execution-later", "pending", 1))

    assert queue.size() == 1
    assert queue.dequeue() == item
    assert queue.dequeue() is None


def test_reconciliation_capacity_must_be_positive():
    with pytest.raises(ValueError, match="max_items must be positive"):
        ReconciliationQueue(max_items=0)

def test_concurrent_queue_producers_cannot_discard_accepted_recovery_items():
    from concurrent.futures import ThreadPoolExecutor

    queue = ReconciliationQueue(max_items=4)
    def submit(index):
        try:
            queue.enqueue(ReconciliationItem(str(index), "retry", 1))
        except OverflowError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=16) as workers:
        admitted = list(workers.map(submit, range(64)))
    assert sum(admitted) == 4
    drained = [queue.dequeue() for _ in range(4)]
    assert len({item.execution_id for item in drained if item is not None}) == 4
    assert queue.dequeue() is None
