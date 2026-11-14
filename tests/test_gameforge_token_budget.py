import pytest
from skeleton.frontier.gameforge_token_budget import TokenBudget


def test_token_budget_is_bounded():
    b = TokenBudget(2)
    assert b.consume()
    assert b.consume()
    assert not b.consume()
    assert b.remaining == 0


def test_token_budget_reset():
    b = TokenBudget(2)
    b.consume(2)
    b.reset()
    assert b.remaining == 2


def test_token_budget_rejects_nonpositive_consumption():
    with pytest.raises(ValueError):
        TokenBudget(2).consume(0)
