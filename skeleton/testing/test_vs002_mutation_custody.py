from __future__ import annotations
import hashlib,pytest
from skeleton.ai.build.engineering_agent import EngineeringError,EngineeringEvidence,EngineeringTask,MutationCustody,VerificationDecision
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def task():return EngineeringTask("TASK.98","bounded change",S("repo"),("skeleton/ai","tests"),("TEST.98",),"git:rollback")
def test_active_lease_records_scoped_change():
 c=MutationCustody();t=task();l=c.acquire(t,"ACTOR.BUILDER");assert c.record(t,l,"CHANGE.1",S("a"),S("b"),("tests",)).fence_token==l.fence_token
def test_parallel_lease_rejected():
 c=MutationCustody();t=task();c.acquire(t,"ACTOR.A")
 with pytest.raises(EngineeringError,match="active mutation lease"):c.acquire(t,"ACTOR.B")
def test_scope_escape_rejected():
 c=MutationCustody();t=task();l=c.acquire(t,"ACTOR.A")
 with pytest.raises(EngineeringError,match="escapes"):c.record(t,l,"CHANGE.1",S("a"),S("b"),("machine/control.json",))
def test_released_lease_cannot_mutate():
 c=MutationCustody();t=task();l=c.acquire(t,"ACTOR.A");c.release(t,l)
 with pytest.raises(EngineeringError,match="stale or inactive"):c.record(t,l,"CHANGE.1",S("a"),S("b"),("tests",))
def test_verifier_must_be_independent():
 with pytest.raises(EngineeringError,match="independent"):EngineeringEvidence("EVID.1",S("task"),S("change"),"ACTOR.A","ACTOR.A",VerificationDecision.PASS,S("tests"),True)
def test_pass_requires_verified_rollback():
 with pytest.raises(EngineeringError,match="rollback"):EngineeringEvidence("EVID.1",S("task"),S("change"),"ACTOR.A","ACTOR.B",VerificationDecision.PASS,S("tests"),False)
def test_noop_change_rejected():
 c=MutationCustody();t=task();l=c.acquire(t,"ACTOR.A")
 with pytest.raises(EngineeringError,match="alter"):c.record(t,l,"CHANGE.1",S("same"),S("same"),("tests",))
