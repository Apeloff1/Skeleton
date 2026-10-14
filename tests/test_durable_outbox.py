import pytest
from skeleton.ai.durable_outbox import OutboxRecord,DeliveryLease,acknowledge,retry_after,OutboxLedger

def rec(g=1,p="p"): return OutboxRecord.create("txn:1","email:1",g,p,10)
def lease(r=None,a=1): return DeliveryLease.issue(r or rec(),"worker",a,100,200)

def test_record_identity_is_deterministic():
 assert rec()==rec()

def test_exact_record_replay_is_idempotent():
 l=OutboxLedger();r=rec();assert l.add(r)==l.add(r)

def test_effect_generation_must_advance_for_changed_effect():
 l=OutboxLedger();l.add(rec())
 with pytest.raises(PermissionError):l.add(rec(p="changed"))
 assert l.add(rec(2,"changed")).generation==2

def test_delivery_requires_live_matching_generation():
 r=rec();x=lease(r);assert acknowledge(r,x,"delivered","e",150).outcome=="delivered"
 with pytest.raises(PermissionError):acknowledge(rec(2),x,"delivered","e",150)
 with pytest.raises(PermissionError):acknowledge(r,x,"delivered","e",200)

def test_clock_reversal_rejected():
 r=rec()
 with pytest.raises(PermissionError):acknowledge(r,lease(r),"failed","e",99)

def test_retry_uses_bounded_exponential_backoff():
 r=rec();a=acknowledge(r,lease(r),"failed","e",150);d=retry_after(r,a,2,200,10,5);assert d.next_attempt==3 and d.not_before_ns==220 and not d.quarantined

def test_poison_effect_is_quarantined_after_bound():
 r=rec();a=acknowledge(r,lease(r,3),"failed","e",150);d=retry_after(r,a,3,200,10,3);assert d.quarantined and d.reason=="poison-quarantine"

def test_retry_requires_failed_matching_ack():
 r=rec();a=acknowledge(r,lease(r),"delivered","e",150)
 with pytest.raises(PermissionError):retry_after(r,a,1,200,10,3)

def test_recovery_pending_excludes_delivered_and_quarantined():
 a=rec();b=OutboxRecord.create("txn:2","email:2",1,"p2",11);l=OutboxLedger((a,b));assert l.pending((a.record_id,),())==(b,);assert l.pending((),(b.record_id,))==(a,)

def test_ack_identity_binds_delivery_evidence():
 r=rec();x=lease(r);a=acknowledge(r,x,"delivered","e1",150);b=acknowledge(r,x,"delivered","e2",150);assert a.ack_id!=b.ack_id
