from skeleton.frontier.gameforge_queue import BoundedQueue


def test_remove_target_preserves_other_items():
    queue = BoundedQueue(3)
    queue.push("first")
    queue.push("second")
    queue.push("third")
    assert queue.remove("second") is True
    assert queue.pop() == "first"
    assert queue.pop() == "third"
    assert queue.remove("missing") is False
