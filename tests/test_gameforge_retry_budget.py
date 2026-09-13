from skeleton.frontier.gameforge_retry_budget import RetryBudget

def test_retry_budget_is_bounded():
 b=RetryBudget(2); assert b.consume(); assert b.consume(); assert not b.consume()
