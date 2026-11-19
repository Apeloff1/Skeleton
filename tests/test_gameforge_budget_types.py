import pytest

from skeleton.frontier.gameforge_budget import Budget


def test_budget_rejects_boolean_capacity():
    with pytest.raises(ValueError):
        Budget(True)


def test_budget_rejects_boolean_amounts():
    budget = Budget(2)
    with pytest.raises(ValueError):
        budget.reserve(True)
    with pytest.raises(ValueError):
        budget.release(True)


def test_budget_respects_capacity():
    budget = Budget(2)
    assert budget.reserve(2)
    assert budget.exhausted
    assert not budget.reserve(1)
