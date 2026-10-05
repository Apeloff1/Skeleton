from __future__ import annotations
import hashlib,pytest
from skeleton.reliability.distributed_execution import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def task(effect=True):return DistributedTask("TASK.102",S("payload"),"IDEMP.102",effect)
def test_stale_worker_cannot_commit_after_reassignment():
 s=DistributedScheduler();t=task(False);a=s.lease(t,"WORKER.A");s.worker_lost(t,a,False);b=s.lease(t,"WORKER.B")
 with pytest.raises(DistributedError,match="stale"):s.commit(t,a,OutcomeState.SUCCEEDED,result_digest=S("old"))
 assert s.commit(t,b,OutcomeState.SUCCEEDED,result_digest=S("new")).state is OutcomeState.SUCCEEDED
def test_unknown_external_effect_is_not_reissuable():
 s=DistributedScheduler();t=task();l=s.lease(t,"WORKER.A");u=s.worker_lost(t,l,True);assert u.state is OutcomeState.UNKNOWN_EXTERNAL;assert not s.may_reissue(t)
def test_unknown_external_reconciles_with_provider_evidence():
 s=DistributedScheduler();t=task();l=s.lease(t,"WORKER.A");u=s.worker_lost(t,l,True);r=s.reconcile(t,u,provider_evidence_digest=S("provider"),result_digest=S("result"));assert r.state is OutcomeState.SUCCEEDED
def test_successful_reconciliation_requires_result():
 s=DistributedScheduler();t=task();l=s.lease(t,"WORKER.A");u=s.worker_lost(t,l,True)
 with pytest.raises(DistributedError,match="requires result"):s.reconcile(t,u,provider_evidence_digest=S("provider"))
def test_non_external_worker_loss_can_be_reissued():
 s=DistributedScheduler();t=task(False);l=s.lease(t,"WORKER.A");assert s.worker_lost(t,l,False) is None;assert s.may_reissue(t)
def test_terminal_task_is_not_leased_again():
 s=DistributedScheduler();t=task(False);l=s.lease(t,"WORKER.A");s.commit(t,l,OutcomeState.SUCCEEDED,result_digest=S("result"));assert s.lease(t,"WORKER.B") is None

def test_idempotency_key_cannot_bind_different_task():
 s=DistributedScheduler();a=task(False);s.lease(a,"WORKER.A")
 b=DistributedTask("TASK.OTHER",S("different"),a.idempotency_key,False)
 with pytest.raises(DistributedError,match="idempotency key reused"):s.lease(b,"WORKER.B")
def test_reconciliation_requires_exact_task_and_active_fence():
 s=DistributedScheduler();t=task();l=s.lease(t,"WORKER.A");u=s.worker_lost(t,l,True)
 other=DistributedTask("TASK.OTHER",S("other"),"IDEMP.OTHER",True)
 with pytest.raises(DistributedError,match="receipt/task mismatch"):s.reconcile(other,u,provider_evidence_digest=S("provider"),result_digest=S("result"))
 s._active[t.task_id]=WorkerLease("LEASE.TASK.102.2",t.digest,"WORKER.B",2)
 with pytest.raises(DistributedError,match="authoritative active lease"):s.reconcile(t,u,provider_evidence_digest=S("provider"),result_digest=S("result"))
def test_terminal_commit_retires_active_lease():
 s=DistributedScheduler();t=task(False);l=s.lease(t,"WORKER.A");s.commit(t,l,OutcomeState.SUCCEEDED,result_digest=S("result"))
 assert t.task_id not in s._active
def test_loss_report_escape_flag_is_strict():
 s=DistributedScheduler();t=task(False);l=s.lease(t,"WORKER.A")
 with pytest.raises(DistributedError,match="must be bool"):s.worker_lost(t,l,1)
 with pytest.raises(DistributedError,match="non-external"):s.worker_lost(t,l,True)
