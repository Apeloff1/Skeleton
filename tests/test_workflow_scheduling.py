import pytest
from skeleton.ai.workflow_scheduling import Worker,Task,schedule,effective_priority,validate_reservation,preempt,reschedule_after_loss,Reservation

def w(i,domain="a",caps=("cpu",),cap=10,res=0,g=1):return Worker(i,g,domain,caps,cap,res)
def t(**kw):
 d=dict(task_id="t",required_capabilities=("cpu",),units=2,base_priority=5,queued_at_ns=0);d.update(kw);return Task(**d)

def test_schedule_is_deterministic_and_capacity_aware():
 a=schedule(1,t(),(w("b",res=5),w("a",res=1)),10,"e",10);assert a.worker_id=="a"

def test_capability_and_antiaffinity_are_enforced():
 x=t(required_capabilities=("gpu",),anti_affinity_domains=("a",));r=schedule(1,x,(w("a",caps=("gpu",)),w("b","b",("gpu",))),10,"e",10);assert r.worker_id=="b"

def test_no_capacity_fails_closed():
 with pytest.raises(PermissionError):schedule(1,t(units=11),(w("a"),),10,"e",10)

def test_priority_aging_is_bounded():
 x=t(base_priority=1);assert effective_priority(x,1000,10,3)==4

def test_reservation_fences_epoch_and_worker_generation():
 r=schedule(2,t(),(w("a"),),10,"e",10);assert validate_reservation(r,w("a"),2)
 with pytest.raises(PermissionError):validate_reservation(r,w("a"),3)
 with pytest.raises(PermissionError):validate_reservation(r,w("a",g=2),2)

def test_capacity_change_invalidates_reservation():
 r=schedule(1,t(units=3),(w("a"),),10,"e",10)
 with pytest.raises(PermissionError):validate_reservation(r,w("a",res=8),1)

def test_preemption_requires_strictly_higher_priority():
 v=Reservation("v",1,"low","a",1,2,5,"e");hi=Reservation("h",1,"high","a",1,2,6,"e")
 assert preempt(1,v,hi,"a",2,"ev").replacement_task_id=="high"
 with pytest.raises(PermissionError):preempt(1,hi,v,"a",2,"ev")

def test_worker_loss_reschedules_under_new_epoch():
 old=schedule(1,t(),(w("a"),w("b","b")),10,"e",10);new=reschedule_after_loss(old,t(),(w("a"),w("b","b")),2,10,"e2");assert new.epoch==2 and new.worker_id=="b"

def test_reschedule_same_epoch_rejected():
 old=schedule(1,t(),(w("a"),),10,"e",10)
 with pytest.raises(PermissionError):reschedule_after_loss(old,t(),(w("b"),),1,10,"e2")
