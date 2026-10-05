from skeleton.frontier.gameforge_budget import Budget


def test_budget_exhaustion_is_explicit():
    budget = Budget(1)
    assert budget.reserve()
    assert budget.exhausted
    assert not budget.reserve()
    budget.release()
    assert budget.remaining == 1
