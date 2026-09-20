"""Regression coverage for bounded reconciliation queue."""

from skeleton.application.reconciliation_queue import ReconciliationQueue


def test_queue_rejects_overflow():
    queue = ReconciliationQueue(max_size=1)
    queue.enqueue("exec-1", attempt=1)

    assert queue.size() == 1

    rejected = queue.enqueue("exec-2", attempt=1)

    assert rejected is False
    assert queue.size() == 1


def test_queue_preserves_execution_identity():
    queue = ReconciliationQueue(max_size=2)
    queue.enqueue("exec-42", attempt=2)

    item = queue.dequeue()

    assert item.execution_id == "exec-42"
    assert item.attempt == 2
