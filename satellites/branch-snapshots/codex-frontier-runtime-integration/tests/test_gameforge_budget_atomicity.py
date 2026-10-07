import pytest

from skeleton.frontier.gameforge_budget import Budget


def test_budget_rejects_boolean_amounts():
    budget = Budget(2)
    with pytest.raises(ValueError):
        budget.reserve(True)
    with pytest.raises(ValueError):
        budget.release(True)


def test_budget_preserves_usage_after_invalid_release():
    budget = Budget(2)
    assert budget.reserve(2)
    with pytest.raises(ValueError):
        budget.release(3)
    assert budget.used == 2
    assert budget.remaining == 0
