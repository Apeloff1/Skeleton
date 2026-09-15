from skeleton.frontier.gameforge_retry_budget import RetryBudget


def test_retry_budget_reports_consumed_attempts():
    budget = RetryBudget(3)
    assert budget.consumed == 0
    assert budget.consume()
    assert budget.consumed == 1
    assert budget.consume()
    assert budget.consumed == 2
    assert budget.reset() == 3
    assert budget.consumed == 0
