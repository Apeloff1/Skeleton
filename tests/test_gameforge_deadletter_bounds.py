import pytest

from skeleton.frontier.gameforge_deadletter import DeadLetterQueue


def test_deadletter_rejects_boolean_capacity():
    with pytest.raises(ValueError):
        DeadLetterQueue(True)


def test_deadletter_never_overwrites_on_saturation():
    queue = DeadLetterQueue(2)
    assert queue.push("a")
    assert queue.push("b")
    assert not queue.push("c")
    assert queue.drain() == ["a", "b"]
    assert len(queue) == 0
