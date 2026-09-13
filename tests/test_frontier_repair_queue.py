import pytest

from frontier.repair_queue import RepairQueue


def test_queue_is_priority_ordered_and_stable():
    queue = RepairQueue()
    queue.push(10, "low")
    queue.push(100, "critical-a")
    queue.push(100, "critical-b")
    assert queue.pop() == "critical-a"
    assert queue.pop() == "critical-b"
    assert queue.pop() == "low"
    assert queue.empty


def test_queue_rejects_invalid_entries():
    queue = RepairQueue()
    with pytest.raises(ValueError):
        queue.push(True, "bad")
    with pytest.raises(ValueError):
        queue.push(1, "")
