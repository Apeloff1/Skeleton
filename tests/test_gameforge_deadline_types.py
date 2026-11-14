import pytest

from skeleton.frontier.gameforge_deadline import Deadline


def test_deadline_rejects_boolean_budget():
    with pytest.raises(ValueError):
        Deadline(True)


def test_deadline_rejects_boolean_cost():
    deadline = Deadline(3)
    with pytest.raises(ValueError):
        deadline.spend(True)


def test_deadline_clamps_failed_spend():
    deadline = Deadline(3)
    assert not deadline.spend(4)
    assert deadline.exhausted
