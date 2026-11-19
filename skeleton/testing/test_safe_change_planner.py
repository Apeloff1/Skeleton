import pytest
from skeleton.ai.safe_change import *
def g(ok=True):return ChangeGate("ownership",ok,"e1")
def s(rev=True):return ChangeStep("stage",rev,"rollback" if rev else None)
def test_gates_and_budget_precede_mutation():SafeChangePlan((s(),),(g(),),2,1,False)
def test_failed_gate_or_budget_rejected():
 with pytest.raises(PermissionError):SafeChangePlan((s(),),(g(False),),2,1,False)
 with pytest.raises(ValueError):SafeChangePlan((s(),),(g(),),0,1,False)
def test_uncertain_change_requires_reversible_stage():
 with pytest.raises(ValueError):SafeChangePlan((s(False),),(g(),),2,1,True)

def test_empty_or_partial_gate_set_fails_closed():
 import pytest
 with pytest.raises(PermissionError):SafeChangePlan((ChangeStep("x",True,"r"),),(),1,1,False)

def test_duplicate_gate_rejected():
 import pytest
 gs=(ChangeGate("ownership",True,"e"),ChangeGate("ownership",True,"e2"),ChangeGate("compatibility",True,"e"),ChangeGate("risk",True,"e"))
 with pytest.raises(ValueError):SafeChangePlan((ChangeStep("s",True,"r"),),gs,1,1,False)
