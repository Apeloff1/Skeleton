import pytest

from skeleton.frontier.gameforge_queue import BoundedQueue


def test_queue_applies_backpressure():
    queue = BoundedQueue(1)
    assert queue.push("x")
    assert not queue.push("y")
    assert queue.peek() == "x"
    assert queue.snapshot() == ("x",)
    assert queue.pop() == "x"
    assert queue.push("y")


def test_queue_requires_capacity():
    with pytest.raises(ValueError):
        BoundedQueue(0)
    with pytest.raises(ValueError):
        BoundedQueue(True)


def test_queue_clear_reports_discarded_items():
    queue = BoundedQueue(3)
    assert queue.push("a")
    assert queue.push("b")
    assert queue.clear() == 2
    assert queue.clear() == 0
    assert queue.remaining == 3


def test_queue_remove_preserves_remaining_order():
    queue = BoundedQueue(3)
    for item in ("a", "b", "c"):
        assert queue.push(item)
    assert queue.remove("b")
    assert queue.snapshot() == ("a", "c")
    assert not queue.remove("missing")
