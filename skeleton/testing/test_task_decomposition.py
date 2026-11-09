import pytest
from skeleton.ai.task_decomposition import *
def s(i,integrate=False,constraints=("policy",),authority="worker"):return Subtask(i,constraints,authority,("done",),integrate)
def test_constraints_and_authority_propagate():
 d=TaskDecomposition("p",("policy",),"worker",(s("a"),s("i",True)),(TaskDependency("a","i"),));assert len(d.subtasks)==2
def test_constraint_or_authority_loss_fails_closed():
 with pytest.raises(ValueError):TaskDecomposition("p",("policy",),"worker",(s("a",True,constraints=()),),())
 with pytest.raises(ValueError):TaskDecomposition("p",("policy",),"worker",(s("a",True,authority="admin"),),())
def test_cycle_missing_integration_and_overdecomposition_rejected():
 with pytest.raises(ValueError):TaskDecomposition("p",(),"worker",(s("a"),s("b",True)),(TaskDependency("a","b"),TaskDependency("b","a")))
 with pytest.raises(ValueError):TaskDecomposition("p",(),"worker",(s("a"),),())
 with pytest.raises(ValueError):TaskDecomposition("p",(),"worker",tuple(s(str(i),i==32) for i in range(33)),(),32)
