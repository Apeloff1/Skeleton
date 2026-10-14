from skeleton.ai.runtime.deferred.tool_governance import *
from skeleton.ai.runtime.deferred.effect_workflows import *
def test_dependency_graph_detects_unavailable_version():
 g=ToolGraph((ToolDependency("a","1","b","2","runtime"),),frozenset({("a","1"),("b","1")}))
 assert not tool_compatibility(g).compatible
def test_health_separates_transport_semantics_and_staleness():
 p=ToolProbe(True,False,True,True,10);assert tool_health(p,10,5).state is ToolHealthState.DEGRADED
 assert tool_health(ToolProbe(True,True,True,True,0),10,5).state is ToolHealthState.STALE
def test_discovery_never_grants_authority():
 r=discover(ToolManifest("t",(ToolCapability("read","1"),),True),True)
 assert r.validated and not r.granted_authority
def test_high_impact_result_requires_independent_validation():
 t=ToolResultTrust("data",ToolEvidence("t","receipt",False))
 assert not validate_result(t,True).accepted and validate_result(t,False).accepted
def test_unknown_effect_outcome_requires_reconciliation():
 a=EffectAttempt(SideEffect("e","op","key","write"),True)
 assert effect_receipt(a,None).state is EffectState.UNKNOWN and effect_receipt(a,None).reconciliation_required
def test_uncommitted_effect_fails_closed():
 a=EffectAttempt(SideEffect("e","op","key","write"),False)
 assert effect_receipt(a,True).reconciliation_required
def test_failed_compensation_becomes_reconciliation_work():
 c=Compensation("c",(CompensationStep("s","e","k"),))
 assert compensation_result(c,(False,)).reconciliation_required
def test_saga_transition_is_durable_and_resumable():
 d=SagaDefinition("s",("a","b"),("ka","kb"),(10,10),(None,"undo-a"))
 i=SagaInstance("s","i",0,7);n,t=advance_saga(d,i)
 assert n.completed==1 and n.durable_revision==8 and t.previous_revision==7
def test_invalid_saga_shape_is_rejected():
 d=SagaDefinition("s",("a",),(),(10,),(None,))
 try:advance_saga(d,SagaInstance("s","i",0,0));assert False
 except ValueError:pass


def test_tool_effect_governance_rejects_ambiguous_identity():
 import pytest
 cycle=ToolGraph((ToolDependency("a","1","b","1","runtime"),ToolDependency("b","1","a","1","runtime")),frozenset({("a","1"),("b","1")}))
 assert not tool_compatibility(cycle).compatible
 assert "dependency-cycle" in tool_compatibility(cycle).unavailable
 with pytest.raises(ValueError): effect_receipt(EffectAttempt(SideEffect("","op","key","write"),True),True)
 bad=Compensation("c",(CompensationStep("s","e","k"),CompensationStep("s","e2","k2")))
 with pytest.raises(ValueError): compensation_result(bad,(True,True))
 duplicate=SagaDefinition("s",("a","a"),("ka","kb"),(10,10),(None,None))
 with pytest.raises(ValueError): advance_saga(duplicate,SagaInstance("s","i",0,0))
 negative=SagaDefinition("s",("a",),("ka",),(-1,),(None,))
 with pytest.raises(ValueError): advance_saga(negative,SagaInstance("s","i",0,0))
