import pytest
from skeleton.ai.admission_transaction import AdmissionIntent,PrepareReceipt,commit,rollback,recover,PARTICIPANTS

def intent(d=100):return AdmissionIntent.create("wf","step",3,d)
def prep(i,p):return PrepareReceipt.create(i,p,3,f"{p}:artifact",f"{p}:evidence")
def allp(i):return tuple(prep(i,p) for p in PARTICIPANTS)

def test_transaction_identity_is_deterministic():
 assert intent()==intent()

def test_prepare_is_generation_fenced():
 i=intent()
 with pytest.raises(PermissionError):PrepareReceipt.create(i,"schedule",2,"a","e")

def test_commit_requires_every_participant():
 i=intent()
 with pytest.raises(PermissionError):commit(i,allp(i)[:-1],10)
 assert commit(i,allp(i),10).transaction_id==i.transaction_id

def test_commit_is_order_independent():
 i=intent();a=commit(i,allp(i),10);b=commit(i,tuple(reversed(allp(i))),10);assert a==b

def test_commit_after_deadline_rejected():
 i=intent(10)
 with pytest.raises(PermissionError):commit(i,allp(i),10)

def test_conflicting_prepare_rejected():
 i=intent();a=prep(i,"schedule");b=PrepareReceipt.create(i,"schedule",3,"other","e")
 with pytest.raises(PermissionError):commit(i,(a,b)+allp(i)[1:],10)

def test_rollback_is_reverse_participant_order():
 i=intent();rs=rollback(i,allp(i),"failure","ev");assert tuple(r.participant for r in rs)==tuple(reversed(PARTICIPANTS))

def test_recovery_validates_commit_evidence():
 i=intent();ps=allp(i);c=commit(i,ps,10);assert recover(i,ps,c,(),20).action=="committed"

def test_recovery_rejects_partial_rollback_history():
 i=intent();ps=allp(i);rs=rollback(i,ps,"failure","ev")
 with pytest.raises(PermissionError):recover(i,ps,None,rs[:-1],20)

def test_expired_incomplete_transaction_requires_rollback():
 i=intent(10);ps=allp(i)[:2];assert recover(i,ps,None,(),10).action=="rollback-required"

def test_live_incomplete_transaction_can_resume():
 i=intent(100);assert recover(i,allp(i)[:1],None,(),10).action=="resume-prepare"
