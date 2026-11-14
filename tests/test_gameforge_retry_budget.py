from skeleton.frontier.gameforge_retry_budget import RetryBudget


def test_retry_budget_is_bounded():
    budget = RetryBudget(2)
    assert budget.consume()
    assert budget.consume()
    assert not budget.consume()
    assert budget.consumed == 2
    assert budget.exhausted


def test_retry_budget_reset_restores_capacity():
    budget = RetryBudget(2)
    assert budget.consume()
    assert budget.reset() == 2
    assert budget.consumed == 0
    assert not budget.exhausted
