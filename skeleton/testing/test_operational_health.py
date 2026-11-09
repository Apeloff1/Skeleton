import pytest
from skeleton.ai.runtime.deferred.operational_health import DependencyHealth,DependencyKind,DependencyRisk,FailoverDecision,HealthBlocker,HealthDimension,HealthScorecard,HealthState,ProviderDependency,ProviderHealth,ProviderOutcome,ProviderProfile,ProviderRisk,decide_failover
D="a"*64
def dim(name="latency",state=HealthState.HEALTHY,score=.99): return HealthDimension(name,state,score,"2026-10-06T00:00:00Z","abc123","prod",D)
def test_scorecard_never_masks_hard_blocker_with_green_average():
 c=HealthScorecard("api",(dim(),dim("errors",score=1.0)),(HealthBlocker("b1","errors","SLO exhausted",D),)); assert c.aggregate_score>.9 and c.state is HealthState.BLOCKED
def test_scorecard_surfaces_unknown(): assert HealthScorecard("worker",(dim(state=HealthState.UNKNOWN),),()).state is HealthState.UNKNOWN
def test_scorecard_rejects_hidden_dimension():
 with pytest.raises(ValueError,match="unknown dimension"): HealthScorecard("api",(dim(),),(HealthBlocker("b1","security","critical",D),))
def test_critical_vulnerable_dependency_requires_disposition():
 with pytest.raises(ValueError,match="risk disposition"): DependencyRisk("pkg","1",DependencyKind.RUNTIME,True,True,True,D)
def test_dependency_health_preserves_kind():
 bad=DependencyRisk("pkg","1",DependencyKind.TRANSITIVE,True,False,False,D,"replace"); assert DependencyHealth(D,(bad,)).blockers==(bad,)
def test_duplicate_dependency_coordinate_is_rejected():
 dep=DependencyRisk("pkg","1",DependencyKind.BUILD,False,True,False,D)
 with pytest.raises(ValueError,match="duplicate"): DependencyHealth(D,(dep,dep))
def test_critical_provider_requires_fallback():
 with pytest.raises(ValueError,match="fallback"): ProviderRisk(ProviderDependency("p1","llm","eu",True),1.0,None,None)
def test_explicit_no_fallback_is_allowed(): assert ProviderRisk(ProviderDependency("p1","llm","eu",True),1.0,None,"disposition").no_fallback_disposition
def test_failover_rejects_incompatible():
 p=ProviderProfile("p1","llm","eu"); hs=(ProviderHealth("p1",False,"t",D),ProviderHealth("p2",True,"t",D),ProviderHealth("p3",True,"t",D)); d=decide_failover(p,(ProviderProfile("p2","llm","us"),ProviderProfile("p3","embedding","eu")),hs,None); assert not d.allowed
def test_unknown_external_outcome_blocks_retry():
 p=ProviderProfile("p1","llm","eu"); d=decide_failover(p,(ProviderProfile("p2","llm","eu"),),(ProviderHealth("p1",False,"t",D),ProviderHealth("p2",True,"t",D)),ProviderOutcome("op","p1",False)); assert d.reason=="unknown external outcome requires reconciliation"
def test_failover_selects_compatible():
 p=ProviderProfile("p1","llm","eu"); d=decide_failover(p,(ProviderProfile("p2","llm","eu"),),(ProviderHealth("p1",False,"t",D),ProviderHealth("p2",True,"t",D)),ProviderOutcome("op","p1",True)); assert d.allowed and d.selected=="p2"
def test_missing_primary_health_fails_closed(): assert not decide_failover(ProviderProfile("p1","llm","eu"),(),(),None).allowed