import pytest
from skeleton.automation.repair_strategy import strategy
def test_escalates_context():assert strategy(1).context_budget<strategy(3).context_budget
def test_fourth_attempt_forbidden():
 with pytest.raises(ValueError):strategy(4)
