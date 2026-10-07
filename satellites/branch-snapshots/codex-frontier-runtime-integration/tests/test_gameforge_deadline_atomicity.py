import pytest

from skeleton.frontier.gameforge_deadline import Deadline


def test_deadline_rejects_boolean_cost():
    deadline = Deadline(3)
    with pytest.raises(ValueError):
        deadline.spend(True)


def test_deadline_exhaustion_is_terminal_until_reset():
    deadline = Deadline(3)
    assert deadline.spend(4) is False
    assert deadline.exhausted
    assert deadline.spend(1) is False
    deadline.reset()
    assert deadline.spend(1)
