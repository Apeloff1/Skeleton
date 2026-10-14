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

def test_task_collections_are_typed_and_bounded():
 with pytest.raises(EngineeringError,match="must be tuple"):EngineeringTask("TASK.X","x",S("repo"),["tests"],("TEST.X",),"rb")
 with pytest.raises(EngineeringError,match="exceeds policy bound"):EngineeringTask("TASK.X","x",S("repo"),tuple(f"p/{i}" for i in range(257)),("TEST.X",),"rb")
def test_runtime_enum_and_boolean_impostors_fail_closed():
 from skeleton.ai.build.engineering_agent import ChangeRecord,LeaseState,MutationLease
 t=task()
 with pytest.raises(EngineeringError,match="LeaseState"):MutationLease("LEASE.X",t.digest,"ACTOR.X",1,t.scope_paths,"active")
 with pytest.raises(EngineeringError,match="VerificationDecision"):EngineeringEvidence("EVID.X",t.digest,S("change"),"ACTOR.A","ACTOR.B","pass",S("tests"),True)
 with pytest.raises(EngineeringError,match="rollback_verified"):EngineeringEvidence("EVID.X",t.digest,S("change"),"ACTOR.A","ACTOR.B",VerificationDecision.FAIL,S("tests"),1)
 with pytest.raises(EngineeringError,match="fence_token"):ChangeRecord("CHANGE.X",t.digest,"LEASE.X",True,S("a"),S("b"),("tests",))
def test_change_digest_binds_custody_and_repository_transition():
 c=MutationCustody();t=task();l=c.acquire(t,"ACTOR.A")
 a=c.record(t,l,"CHANGE.1",S("a"),S("b"),("tests",))
 b=c.record(t,l,"CHANGE.2",S("a"),S("b"),("tests",))
 assert a.digest!=b.digest
 assert len(a.digest)==64
def test_mutation_paths_require_typed_nonempty_tuple():
 c=MutationCustody();t=task();l=c.acquire(t,"ACTOR.A")
 with pytest.raises(EngineeringError,match="non-empty tuple"):c.record(t,l,"CHANGE.1",S("a"),S("b"),[])

def test_acceptance_requires_exact_change_and_passing_independent_evidence():
 from skeleton.ai.build.engineering_agent import accept_change
 c=MutationCustody();t=task();l=c.acquire(t,"ACTOR.BUILDER");change=c.record(t,l,"CHANGE.1",S("a"),S("b"),("tests",))
 good=EngineeringEvidence("EVID.1",t.digest,change.digest,"ACTOR.BUILDER","ACTOR.VERIFIER",VerificationDecision.PASS,S("tests"),True)
 accepted=accept_change(t,change,good);assert accepted.change_digest==change.digest
 wrong=EngineeringEvidence("EVID.2",t.digest,S("other"),"ACTOR.BUILDER","ACTOR.VERIFIER",VerificationDecision.PASS,S("tests"),True)
 with pytest.raises(EngineeringError,match="evidence/change"):accept_change(t,change,wrong)
 failed=EngineeringEvidence("EVID.3",t.digest,change.digest,"ACTOR.BUILDER","ACTOR.VERIFIER",VerificationDecision.FAIL,S("tests"),True)
 with pytest.raises(EngineeringError,match="failed verification"):accept_change(t,change,failed)
