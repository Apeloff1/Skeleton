import pytest
from skeleton.observability.tool_health import ToolProbe,ToolHealthState,ToolHealth
from skeleton.persistence.side_effect_ledger import SideEffect
from skeleton.reliability.compensation import Compensation,CompensationStep
from skeleton.ai.effect_governance import authorize_effect

def health(ok=True): return ToolHealth(ToolProbe("probe",True,10),ToolHealthState(ok,ok,ok,ok))
def comp(effect="e"): return Compensation("op",(CompensationStep("undo",effect,"undo"),))
def test_authorization_binds_health_effect_and_compensation():
 a,r=authorize_effect("op",SideEffect("e","write","key"),health(),comp(),now=11,max_health_age=5)
 assert a.state=="pending" and r.effect_id=="e" and len(r.authorization_digest)==64
def test_stale_health_fails_closed():
 with pytest.raises(PermissionError,match="health"): authorize_effect("op",SideEffect("e","write","key"),health(),comp(),now=20,max_health_age=5)
def test_wrong_compensation_fails_closed():
 with pytest.raises(PermissionError,match="compensation"): authorize_effect("op",SideEffect("e","write","key"),health(),comp("other"),now=11,max_health_age=5)
