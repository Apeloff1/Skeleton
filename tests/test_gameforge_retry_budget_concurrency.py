from concurrent.futures import ThreadPoolExecutor

from skeleton.frontier.gameforge_retry_budget import RetryBudget


def test_retry_budget_never_consumes_below_zero_under_contention():
    budget = RetryBudget(32)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: budget.consume(), range(128)))
    assert sum(results) == 32
    assert budget.remaining == 0
    assert budget.exhausted


def test_retry_budget_reset_restores_capacity():
    budget = RetryBudget(3)
    assert [budget.consume() for _ in range(4)] == [True, True, True, False]
    assert budget.consumed == 3
    assert budget.reset() == 3
    assert budget.consumed == 0
