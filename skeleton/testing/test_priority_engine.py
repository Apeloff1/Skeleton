from __future__ import annotations
import pytest
from skeleton.automation.priority_engine import *
def f(i="FACTOR.RISK",v=.8,w=5,p="RISK.1"):return PriorityInput(i,p,v,w)
def test_hard_blocker_is_separate_from_soft_score():
 e=PriorityEngine();d=e.decide("ITEM.1",(f(),),(PriorityConstraint("BLOCK.DEP",ConstraintKind.HARD_BLOCKER,True,"DEP.1","dependency open"),))
 assert d.blocked and d.score==4.0
def test_inactive_blocker_does_not_block():
 d=PriorityEngine().decide("ITEM.1",(f(),),(PriorityConstraint("BLOCK.DEP",ConstraintKind.HARD_BLOCKER,False,"DEP.1","resolved"),));assert not d.blocked
def test_factor_bounds_prevent_unbounded_gaming():
 with pytest.raises(PriorityError,match="weight"):f(w=100)
 with pytest.raises(PriorityError,match="value"):f(v=2)
def test_factor_requires_provenance():
 with pytest.raises(PriorityError,match="stable identifier"):f(p="free text")
def test_duplicate_factor_rejected():
 with pytest.raises(PriorityError,match="duplicate"):PriorityEngine().decide("ITEM.1",(f(),f()))
def test_age_boost_prevents_indefinite_starvation_and_is_capped():
 e=PriorityEngine(max_age_boost=2,age_step=.5);d=e.decide("ITEM.1",(),age_epochs=100);assert d.age_boost==2 and d.effective_score==2
def test_hysteresis_suppresses_small_oscillation():
 e=PriorityEngine(hysteresis=.5);d=e.decide("ITEM.1",(f(v=.51,w=1),),previous_score=.5);assert d.effective_score==.5
def test_large_change_reprioritizes():
 e=PriorityEngine(hysteresis=.1);d=e.decide("ITEM.1",(f(v=1,w=2),),previous_score=.5);assert d.effective_score==2
def test_rank_places_unblocked_before_blocked_even_with_higher_blocked_score():
 e=PriorityEngine();open_=e.decide("ITEM.OPEN",(f(v=.1,w=1),));blocked=e.decide("ITEM.BLOCKED",(f(v=1,w=10),),(PriorityConstraint("BLOCK.X",ConstraintKind.HARD_BLOCKER,True,"DEP.X","blocked"),))
 assert e.rank((blocked,open_))[0].item_id=="ITEM.OPEN"
def test_rank_is_deterministic_on_ties():
 e=PriorityEngine();a=e.decide("ITEM.A",());b=e.decide("ITEM.B",());assert [x.item_id for x in e.rank((b,a))]==["ITEM.A","ITEM.B"]
def test_negative_age_rejected():
 with pytest.raises(PriorityError,match="negative"):PriorityEngine().decide("ITEM.1",(),age_epochs=-1)

@pytest.mark.parametrize("field,value",[
 ("value",float("nan")),("value",float("inf")),("weight",float("-inf"))
])
def test_nonfinite_factor_values_are_rejected(field,value):
 kw={"v":.5,"w":1};kw[{"value":"v","weight":"w"}[field]]=value
 with pytest.raises(PriorityError,match="finite numeric"):f(**kw)

def test_duplicate_constraints_are_rejected():
 c=PriorityConstraint("BLOCK.X",ConstraintKind.HARD_BLOCKER,True,"DEP.X","blocked")
 with pytest.raises(PriorityError,match="duplicate priority constraint"):
  PriorityEngine().decide("ITEM.1",(),(c,c))

def test_constraint_policy_inputs_are_typed():
 with pytest.raises(PriorityError,match="ConstraintKind"):PriorityConstraint("BLOCK.X","hard_blocker",True,"DEP.X","blocked")
 with pytest.raises(PriorityError,match="active must be bool"):PriorityConstraint("BLOCK.X",ConstraintKind.HARD_BLOCKER,1,"DEP.X","blocked")

def test_decision_inputs_are_typed_and_bounded():
 with pytest.raises(PriorityError,match="typed tuple"):PriorityEngine().decide("ITEM.1",[f()])
 with pytest.raises(PriorityError,match="cardinality"):PriorityEngine().decide("ITEM.1",tuple(f(f"FACTOR.X{i}") for i in range(257)))

def test_age_and_previous_score_are_canonical_numeric_inputs():
 with pytest.raises(PriorityError,match="non-negative integer"):PriorityEngine().decide("ITEM.1",(),age_epochs=1.5)
 with pytest.raises(PriorityError,match="finite numeric"):PriorityEngine().decide("ITEM.1",(),previous_score=float("nan"))
