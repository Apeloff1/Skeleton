import pytest

from skeleton.frontier.gameforge_retry_budget import RetryBudget


def test_retry_budget_rejects_bool_attempts():
    with pytest.raises(ValueError):
        RetryBudget(True)


def test_retry_budget_accepts_zero_attempts():
    budget = RetryBudget(0)
    assert budget.exhausted
    assert budget.consumed == 0
    assert not budget.consume()
