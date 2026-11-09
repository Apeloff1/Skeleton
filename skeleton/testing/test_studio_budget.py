import pytest
from skeleton.automation.studio_budget import ExecutionBudget
def test_budget_consumes_immutably():
 b=ExecutionBudget(model_calls=2); n=b.consume(model_calls=1); assert b.model_calls==2 and n.model_calls==1
def test_budget_fails_closed():
 with pytest.raises(ValueError): ExecutionBudget(model_calls=1).consume(model_calls=2)
