import pytest

from skeleton.frontier.gameforge_queue import BoundedQueue


def test_queue_rejects_boolean_capacity():
    with pytest.raises(ValueError):
        BoundedQueue(True)


def test_queue_clear_restores_capacity():
    queue = BoundedQueue(2)
    assert queue.push("a")
    assert queue.push("b")
    assert queue.full
    queue.clear()
    assert len(queue) == 0
    assert queue.remaining == 2
    assert not queue.full
