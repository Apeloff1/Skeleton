import pytest
from skeleton.ai.workflow_recovery import Step,WorkflowPlan,StepCheckpoint,recover,compensation_order,terminal_receipt

def plan(deadline=100):return WorkflowPlan.create("wf",deadline,(Step("a",1,()),Step("b",1,("a",)),Step("c",1,("b",))))
def cp(p,s,o="committed",e=None):return StepCheckpoint.create(p,s,1,o,e or f"e:{s}:{o}")

def test_plan_identity_is_order_independent():
 p=plan();q=WorkflowPlan.create("wf",100,tuple(reversed(p.steps)));assert p==q

def test_cycles_and_unknown_dependencies_rejected():
 with pytest.raises(ValueError):WorkflowPlan.create("wf",100,(Step("a",1,("b",)),Step("b",1,("a",))))
 with pytest.raises(ValueError):WorkflowPlan.create("wf",100,(Step("a",1,("x",)),))

def test_recovery_exposes_only_dependency_ready_steps():
 p=plan();assert recover(p,(),0)==("running",(),("a",))
 assert recover(p,(cp(p,"a"),),1)==("running",(),("b",))

def test_failed_step_enters_reverse_dependency_compensation():
 p=plan();state,order,_=recover(p,(cp(p,"a"),cp(p,"b"),cp(p,"c","failed")),10);assert state=="compensating" and order==("b","a")

def test_deadline_enters_compensation():
 p=plan();state,order,_=recover(p,(cp(p,"a"),),100);assert state=="compensating" and order==("a",)

def test_generation_fence_rejects_stale_checkpoint():
 p=plan()
 with pytest.raises(PermissionError):StepCheckpoint.create(p,"a",0,"committed","e")

def test_foreign_or_conflicting_checkpoint_rejected():
 p=plan();q=WorkflowPlan.create("other",100,(Step("a",1,()),))
 with pytest.raises(PermissionError):recover(p,(cp(q,"a"),),0)
 with pytest.raises(PermissionError):recover(p,(cp(p,"a"),cp(p,"a",e="other")),0)

def test_terminal_success_requires_every_step_committed():
 p=plan()
 with pytest.raises(PermissionError):terminal_receipt(p,(cp(p,"a"),),"committed")
 r=terminal_receipt(p,tuple(cp(p,x) for x in ("a","b","c")),"committed");assert r.outcome=="committed"

def test_compensation_order_respects_reverse_dependencies():
 p=plan();assert compensation_order(p,("a","b","c"))==("c","b","a")
