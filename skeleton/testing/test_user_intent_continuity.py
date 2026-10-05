import pytest
from skeleton.ai.user_intent import *
def i(n,v,auth=True):return UserIntent(n,"instruction",(IntentConstraint("scope",v),),auth,"summary")
def test_authoritative_instruction_is_separate_from_inference():
 x=i("1","repo");assert x.instruction=="instruction" and x.inferred_summary=="summary"
def test_conflicting_new_instruction_is_detected():
 assert reconcile_intent(i("1","repo"),i("2","workspace"))==("scope",)
def test_inference_cannot_supersede_authoritative_intent():
 with pytest.raises(PermissionError):reconcile_intent(i("1","repo"),i("2","repo",False))
def test_revision_requires_explicit_lineage_reason():
 with pytest.raises(ValueError):IntentRevision("1",i("1","repo"),"")

def test_dropped_constraint_is_explicit_conflict():
 a=UserIntent("a","do",(IntentConstraint("scope","safe"),),True)
 b=UserIntent("b","do",(),True)
 assert reconcile_intent(a,b)==("scope",)

def test_non_authoritative_current_lineage_cannot_be_reconciled():
 import pytest
 a=UserIntent("a","x",(),False);b=UserIntent("b","y",(),True)
 with pytest.raises(PermissionError):reconcile_intent(a,b)
