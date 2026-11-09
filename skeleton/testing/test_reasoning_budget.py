import pytest
from skeleton.observability.reasoning_cost import ReasoningStage,attribute
from skeleton.ai.reasoning_budget import ReasoningBudget,admit_reasoning
S=ReasoningStage("s","plan","m","1")
def test_budget_admits_bounded_cost(): assert admit_reasoning(ReasoningBudget("op","compute",5),(attribute("op",S,2),),attribute("op",ReasoningStage("s2","act","m","1"),3))==5
def test_budget_fails_closed(): 
 with pytest.raises(PermissionError,match="exceeded"): admit_reasoning(ReasoningBudget("op","compute",4),(attribute("op",S,2),),attribute("op",ReasoningStage("s2","act","m","1"),3))
def test_cross_operation_rejected():
 with pytest.raises(PermissionError,match="cross-operation"): admit_reasoning(ReasoningBudget("op","compute",5),(),attribute("other",S,1))
