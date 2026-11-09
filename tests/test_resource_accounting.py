import pytest
from skeleton.ai.resource_accounting import Resources,Quota,Reservation,ResourceLedger

def ledger():return ResourceLedger((Quota("tenant",None,Resources(10,2,100,1000),Resources(2,1,20,100)),Quota("project","tenant",Resources(6,1,80,800),Resources(1,0,10,50)),Quota("workflow","project",Resources(4,1,60,600),Resources())))
def r(cpu=2,g=1,d=100,e="ev"):return Reservation.create(("tenant","project","workflow"),g,Resources(cpu,0,10,10),d,e)

def test_hierarchical_admission_accounts_all_scopes():
 l=ledger();x=l.admit(r(),0);assert l.used["tenant"].cpu==2 and l.used["workflow"].cpu==2 and x==r()

def test_child_quota_fails_closed_even_if_parent_has_capacity():
 l=ledger();l.admit(r(4),0)
 with pytest.raises(PermissionError):l.admit(r(1,2,e="e2"),0)

def test_expired_deadline_rejected():
 with pytest.raises(PermissionError):ledger().admit(r(d=10),10)

def test_burst_requires_explicit_bounded_credit():
 l=ledger();l.admit(r(4),0)
 x=Reservation.create(("tenant","project"),2,Resources(3),100,"e2")
 with pytest.raises(PermissionError):l.admit(x,0)
 assert l.admit(x,0,{"tenant":Resources(2),"project":Resources(1)}).reservation_id==x.reservation_id

def test_release_is_generation_fenced_and_idempotent():
 l=ledger();x=l.admit(r(),0);a=l.release(x.reservation_id,1,"release:e");b=l.release(x.reservation_id,1,"release:e");assert a==b and l.used["tenant"].cpu==0
 with pytest.raises(PermissionError):l.release(x.reservation_id,2,"release:e")

def test_release_replay_cannot_change_evidence():
 l=ledger();x=l.admit(r(),0);l.release(x.reservation_id,1,"a")
 with pytest.raises(PermissionError):l.release(x.reservation_id,1,"b")

def test_crash_reconciliation_finds_only_orphaned_active_reservations():
 l=ledger();a=l.admit(r(),0);b=l.admit(r(1,2,e="e2"),0);assert l.leaked((b.reservation_id,))==(a,)

def test_resource_underflow_fails_closed():
 with pytest.raises(PermissionError):Resources(1).sub(Resources(2))
