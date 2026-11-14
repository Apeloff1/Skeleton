from skeleton.frontier.gameforge_retry_budget import RetryBudget


def test_retry_budget_tracks_capacity_and_reset():
    budget = RetryBudget(2)
    assert not budget.exhausted
    assert budget.consume()
    assert budget.consume()
    assert budget.exhausted
    assert not budget.consume()
    budget.reset()
    assert budget.remaining == 2
    assert budget.consume()
