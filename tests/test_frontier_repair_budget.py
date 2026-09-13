import pytest

from frontier.repair_budget import WorkBudget


def test_budget_consumes_without_overrun():
    budget = WorkBudget(3)
    assert budget.consume(2) is True
    assert budget.spent == 2
    assert budget.remaining == 1
    assert budget.consume(2) is False
    assert budget.remaining == 1


def test_budget_rejects_boolean_inputs():
    with pytest.raises(ValueError):
        WorkBudget(True)
    with pytest.raises(ValueError):
        WorkBudget(2).consume(True)
