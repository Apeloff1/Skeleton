from skeleton.frontier.gameforge_queue import BoundedQueue


def test_queue_pressure_state():
    queue = BoundedQueue(2)
    assert queue.remaining == 2
    assert not queue.full
    assert queue.push("a")
    assert queue.peek() == "a"
    assert queue.push("b")
    assert queue.full
    assert queue.remaining == 0
    assert queue.pop() == "a"
    assert not queue.full
    assert queue.remaining == 1
