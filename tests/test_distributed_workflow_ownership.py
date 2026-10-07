import pytest
from skeleton.ai.distributed_workflow_ownership import CoordinatorEpoch,StepLease,Heartbeat,validate_execution,adopt_orphan,reconcile_leases

def ep(n=1,c="c"):return CoordinatorEpoch.create("wf",c,n,n*10)
def lease(e=None,w="w",g=1,start=20,end=40):return StepLease.issue(e or ep(),"s",w,g,start,end)

def test_live_matching_owner_is_valid():
 e=ep();x=lease(e);assert validate_execution(e,x,"w",1,30)

def test_stale_coordinator_and_worker_are_fenced():
 e=ep();x=lease(e)
 with pytest.raises(PermissionError):validate_execution(ep(2),x,"w",1,30)
 with pytest.raises(PermissionError):validate_execution(e,x,"w",2,30)

def test_expired_or_preissue_execution_rejected():
 e=ep();x=lease(e)
 with pytest.raises(PermissionError):validate_execution(e,x,"w",1,19)
 with pytest.raises(PermissionError):validate_execution(e,x,"w",1,40)

def test_heartbeat_must_be_inside_lease():
 x=lease()
 assert Heartbeat.create(x,30).lease_id==x.lease_id
 with pytest.raises(PermissionError):Heartbeat.create(x,40)

def test_live_owner_cannot_be_adopted():
 old=ep();x=lease(old);new=ep(2,"c2")
 with pytest.raises(PermissionError):adopt_orphan(old,x,None,new,"w2",1,39,"ev",10)

def test_expired_orphan_takeover_binds_old_and_new_ownership():
 old=ep();x=lease(old);hb=Heartbeat.create(x,30);new=ep(2,"c2");nl,r=adopt_orphan(old,x,hb,new,"w2",3,40,"ev",10)
 assert nl.coordinator_epoch==2 and nl.worker_generation==3 and r.old_lease_id==x.lease_id and r.new_lease_id==nl.lease_id

def test_takeover_requires_newer_epoch():
 old=ep();x=lease(old)
 with pytest.raises(PermissionError):adopt_orphan(old,x,None,ep(1,"other"),"w2",2,40,"ev",10)

def test_foreign_heartbeat_rejected():
 old=ep();x=lease(old);other=lease(old,w="other")
 hb=Heartbeat.create(other,30)
 with pytest.raises(PermissionError):adopt_orphan(old,x,hb,ep(2),"w2",2,40,"ev",10)

def test_split_brain_same_epoch_rejected():
 e=ep();a=lease(e,"a");b=lease(e,"b")
 with pytest.raises(PermissionError):reconcile_leases((a,b))

def test_exact_lease_replay_reconciles_deterministically():
 x=lease();assert reconcile_leases((x,x))==(x,)
