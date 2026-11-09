from skeleton.ai.runtime.deferred.scheduling_autonomy import *
A=frozenset({"read"});C=frozenset({"safe"})
def dec():
 return TaskDecomposition(A,C,(Subtask("a",2,A,C),Subtask("b",3,A,C,True)),(TaskDependency("a","b"),))
def test_decomposition_preserves_authority_constraints_and_integration():
 assert validate_decomposition(dec())
 bad=TaskDecomposition(A,C,(Subtask("x",1,frozenset({"write"}),C,True),),())
 assert not validate_decomposition(bad)
def test_decomposition_rejects_cycles():
 d=TaskDecomposition(A,C,(Subtask("a",1,A,C),Subtask("b",1,A,C,True)),(TaskDependency("a","b"),TaskDependency("b","a")))
 assert not validate_decomposition(d)
def test_critical_path_uses_dependency_and_duration_data():
 p=critical_path(dec());assert p.task_ids==("a","b") and p.duration==5
def test_scheduler_requires_dependencies_lease_and_worker_authority():
 d=dec();s=schedule_ready(d,set(),("w",),{"w"}, {"w":A});assert [x.task_id for x in s.assignments]==["a"]
 assert not schedule_ready(d,set(),("w",),set(),{"w":A}).assignments
def test_simulation_is_non_authoritative_and_labels_assumptions():
 s=SchedulingSimulation(WorkloadTrace((1,2),("historical",)),SchedulingPolicy("fifo"),SimulationMetric(1,2,.9,3))
 assert not s.authoritative and s.trace.assumptions
def test_controller_cannot_exceed_policy_authority_or_bound():
 c=AutonomyController(10,2);s=ControlState(0,1,10)
 assert control(c,s,policy_allowed=True,authority_allowed=True).adjustment==2
 assert control(c,s,policy_allowed=False,authority_allowed=True).adjustment==0
 assert control(c,s,policy_allowed=True,authority_allowed=False).adjustment==0
def test_controller_stops_when_resource_bound_exhausted():
 assert control(AutonomyController(1,1),ControlState(0,1,0),policy_allowed=True,authority_allowed=True).adjustment==0
def test_escalation_requires_eligibility_and_explicit_approval():
 r=AutonomyEscalation("r",frozenset({"write"}),EscalationEvidence(True,None));assert grant_escalation(r,"later") is None
 g=grant_escalation(AutonomyEscalation("r",frozenset({"write"}),EscalationEvidence(True,"approval")),"later")
 assert g and g.expires_at=="later" and not g.revoked


def test_scheduling_autonomy_depth_invariants_fail_closed():
 import pytest
 t=Subtask("t",1,frozenset({"run"}),frozenset(),True)
 assert not validate_decomposition(TaskDecomposition(frozenset({"run"}),frozenset(),(t,),(TaskDependency("t","t"),)))
 d=TaskDecomposition(frozenset({"run"}),frozenset(),(t,),())
 with pytest.raises(ValueError):schedule_ready(d,set(),("w","w"),{"w"}, {"w":frozenset({"run"})})
 with pytest.raises(ValueError):schedule_ready(d,{"unknown"},("w",),{"w"},{"w":frozenset({"run"})})
 with pytest.raises(ValueError):control(AutonomyController(-1,1),ControlState(0,1,1),policy_allowed=True,authority_allowed=True)
 with pytest.raises(ValueError):control(AutonomyController(1,1),ControlState(0,1,-1),policy_allowed=True,authority_allowed=True)
 assert grant_escalation(AutonomyEscalation("",frozenset({"run"}),EscalationEvidence(True,"receipt")),"later") is None
 assert grant_escalation(AutonomyEscalation("r",frozenset(),EscalationEvidence(True,"receipt")),"later") is None
