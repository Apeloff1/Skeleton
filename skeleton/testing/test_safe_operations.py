import pytest
from skeleton.ai.runtime.deferred.safe_operations import *
D="a"*64; B="b"*64
def test_repair_completion_requires_bound_checkpoint_and_verified_invariant():
 p=SafeRepairPlan("r",D,D,D,"healthy"); c=RepairCheckpoint("r",D,True); e=RepairEvidence("r",B,True,D)
 assert admit_repair_completion(p,c,e)
 assert not admit_repair_completion(p,RepairCheckpoint("r",B,True),e)
 assert not admit_repair_completion(p,c,RepairEvidence("r",B,False,D))
def test_twin_is_never_authoritative_and_requires_governed_observations_for_current():
 assert not DigitalTwin("t",(TwinObservation("db",D,"now",.1,True),)).authoritative
 assert not DigitalTwin("t",(TwinObservation("db",D,"now",.1,False),)).current
def test_twin_scenario_cannot_authorize_real_effect():
 with pytest.raises(ValueError): TwinScenario("s","t",("delete",),False)
def test_deployment_planner_cannot_self_authorize():
 with pytest.raises(ValueError): DeploymentProposal("p",True,1,1,.99,True)
def test_deployment_respects_compatibility_resources_blast_radius_and_slo():
 c=DeploymentConstraint(2,.99,4)
 assert plan_deployment(DeploymentProposal("p",True,4,2,.99),c)
 assert plan_deployment(DeploymentProposal("p",False,1,1,1),c) is None
 assert plan_deployment(DeploymentProposal("p",True,5,1,1),c) is None
 assert plan_deployment(DeploymentProposal("p",True,1,3,1),c) is None
def test_scheduler_reserves_before_admission_and_preserves_owner():
 r=ResourceRequest("r","tenant",2,4,1); d=place(r,2,4,"lease","later")
 assert d.admitted and d.lease.owner=="tenant"
 assert not place(r,1,4,"lease","later").admitted
def test_resource_request_rejects_zero_or_negative():
 with pytest.raises(ValueError): ResourceRequest("r","x",0,1,1)
def test_fairness_aging_is_bounded():
 p=FairnessPolicy(10,1); s=QueueShare("t",1,0,1)
 assert fairness(p,s,StarvationSignal("t",100,True),security_allowed=True).boost==1
def test_fairness_never_overrides_security():
 p=FairnessPolicy(0,10); s=QueueShare("t",1,0,1)
 d=fairness(p,s,StarvationSignal("t",100,True),security_allowed=False)
 assert d.boost==0 and not d.safety_override


def test_safe_operations_depth_invariants_fail_closed():
 import pytest
 d="a"*64
 with pytest.raises(ValueError):SafeRepairPlan("",d,d,d,"inv")
 p=SafeRepairPlan("r",d,d,d,"inv")
 assert not admit_repair_completion(p,RepairCheckpoint("r",d,True),RepairEvidence("r",d,True,"bad"))
 with pytest.raises(ValueError):TwinObservation("c","bad","now",0.1,True)
 assert plan_deployment(DeploymentProposal("p",True,1,0,1),DeploymentConstraint(-1,0.9,1)) is None
 with pytest.raises(ValueError):ResourceRequest("","o",1,1,1)
 r=ResourceRequest("r","o",1,1,1);assert not place(r,-1,1,"l","later").admitted
 with pytest.raises(ValueError):fairness(FairnessPolicy(1,1),QueueShare("t",1,0,0),StarvationSignal("other",1,True),security_allowed=True)
