from skeleton.ai.runtime.deferred.control_plane import *
def test_ambiguous_high_impact_objective_is_not_executable_without_clarification():
 o=Objective("o","change prod",(),ObjectiveState.REQUESTED)
 assert not NormalizedObjective(o,(),(ObjectiveAmbiguity("which prod",True),),False).executable
def test_hard_constraint_cannot_be_traded_for_utility():
 cs=ConstraintSet((Constraint("safety",ConstraintStrength.HARD,"safe","policy"),))
 r=evaluate_constraints(cs,{"safety":False}); c=DecisionContext("o",r,(DecisionOption("fast",True,999,(),0),))
 assert decide(c).option_id is None
def test_decision_optimizes_only_after_admissibility():
 r=ConstraintResult(True,(),()); opts=(DecisionOption("bad",False,99,(),0),DecisionOption("good",True,1,(),0))
 assert decide(DecisionContext("o",r,opts)).option_id=="good"
def test_decision_record_supersession_is_append_only_contract():
 old=DecisionRecord("r1",Decision("a","x"),"d"); new=DecisionRecord("r2",Decision("b","correction"),"e","r1")
 assert old.record_id=="r1" and new.supersedes=="r1"
def test_workflow_identity_binds_authority_retry_timeout_and_compensation():
 a=WorkflowIR("1",(WorkflowNode("n","tool",("read",),1,10,None),),())
 b=WorkflowIR("1",(WorkflowNode("n","tool",("write",),1,10,None),),())
 assert a.identity!=b.identity
def test_workflow_node_rejects_unbounded_invalid_runtime_values():
 try: WorkflowNode("n","x",(),-1,0,None); assert False
 except ValueError: pass
def test_control_plane_requires_independent_policy_and_authority_gates():
 w=WorkflowIR("1",(WorkflowNode("n","x",(),0,1,None),),()); c=ControlPlaneCommand("c",w,"o","p","a")
 s=ControlPlaneState(1,None,None,"seed")
 for p,a in ((False,True),(True,False)):
  ns,r=apply_command(s,c,policy_valid=p,authority_valid=a); assert ns==s and not r.accepted
def test_control_plane_state_is_durable_revision_chain():
 w=WorkflowIR("1",(WorkflowNode("n","x",(),0,1,None),),()); c=ControlPlaneCommand("c",w,"o","p","a")
 s=ControlPlaneState(1,None,None,"seed"); ns,r=apply_command(s,c,policy_valid=True,authority_valid=True)
 assert r.accepted and ns.revision==2 and ns.durable_state_digest!="seed"


def test_control_plane_depth_invariants_fail_closed():
 import pytest
 con=Constraint("c",ConstraintStrength.HARD,"p","src")
 with pytest.raises(ValueError):evaluate_constraints(ConstraintSet((con,con)),{"c":True})
 cr=ConstraintResult(True,(),())
 opts=(DecisionOption("b",True,1,("e",),0.1),DecisionOption("a",True,1,("e",),0.1))
 assert decide(DecisionContext("o",cr,opts)).option_id=="a"
 n=WorkflowNode("n","cap",(),0,1,None)
 bad=WorkflowIR("1",(n,),(WorkflowEdge("n","missing"),))
 with pytest.raises(ValueError):_=bad.identity
 state=ControlPlaneState(0,None,"cmd","digest")
 good=WorkflowIR("1",(n,),())
 cmd=ControlPlaneCommand("cmd",good,"o","p","a")
 ns,r=apply_command(state,cmd,policy_valid=True,authority_valid=True);assert ns==state and not r.accepted
 with pytest.raises(ValueError):apply_command(ControlPlaneState(-1,None,None,"digest"),ControlPlaneCommand("x",good,"o","p","a"),policy_valid=True,authority_valid=True)
