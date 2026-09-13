from skeleton.frontier.gameforge_admission import Admission
from skeleton.frontier.gameforge_budget import Budget
from skeleton.frontier.gameforge_circuit import Circuit
from skeleton.frontier.gameforge_coordinator import RuntimeCoordinator
from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_health_score import HealthScore
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_quota import Quota
from skeleton.frontier.gameforge_queue import BoundedQueue
from skeleton.frontier.gameforge_rate import RateWindow
from skeleton.frontier.gameforge_retry_budget import RetryBudget

def make(queue_capacity=1,retries=0,threshold=2):
 s=ServiceLifecycle(); d=DependencyGate(("db",)); r=RateWindow(2,10); c=Circuit(threshold); b=Budget(1); q=Quota(1); queue=BoundedQueue(queue_capacity); rb=RetryBudget(retries); h=HealthScore(4); return RuntimeCoordinator(s,d,r,c,b,q,queue,rb,h),s,d

def test_coordinator_fails_closed_until_ready():
 x,s,d=make(); assert x.admit(0,0,"x") is Admission.SHED; s.ready(); d.mark("db"); assert x.admit(0,0,request_id="x") is Admission.ACCEPT

def test_coordinator_composes_budget_and_rate():
 x,s,d=make(); s.ready(); d.mark("db"); assert x.admit(0,0,request_id="x") is Admission.ACCEPT; assert x.admit(1,0,request_id="y") is Admission.SHED; x.release(); assert x.admit(1,0,request_id="z") is Admission.ACCEPT

def test_coordinator_quota_rejects_without_leaking_budget():
 x,s,d=make(); x.quota.limit=0; s.ready(); d.mark("db"); assert x.admit(0,0,request_id="x") is Admission.SHED; assert x.budget.used==0

def test_coordinator_queue_rejects_without_leaking_reservations():
 x,s,d=make(); x.queue.capacity=0; s.ready(); d.mark("db"); assert x.admit(0,0,request_id="x") is Admission.SHED; assert x.budget.used==0; assert x.quota.used==0

def test_coordinator_retry_budget_bounds_retries():
 x,s,d=make(retries=1); s.ready(); d.mark("db"); assert x.admit(0,0,request_id="x",retry=True) is Admission.ACCEPT; x.release(); assert x.admit(1,0,request_id="y",retry=True) is Admission.SHED

def test_coordinator_health_records_admission_outcomes():
 x,s,d=make(); s.ready(); d.mark("db"); assert x.admit(0,0,request_id="x") is Admission.ACCEPT; assert x.health.value==1.0; x.release(); x.lifecycle.drain(); assert x.admit(1,0,request_id="y") is Admission.SHED; assert x.health.value==0.5

def test_coordinator_snapshot_is_immutable_state():
 x,s,d=make(); s.ready(); d.mark("db"); x.admit(0,0,request_id="x"); snap=x.snapshot(active=1); assert snap.lifecycle=="ready"; assert snap.dependencies_ready; assert snap.budget_used==1; assert snap.quota_used==1; assert snap.queue_depth==1; assert snap.health==1.0; assert snap.saturated()

def test_coordinator_receipt_is_observable():
 x,s,d=make(); s.ready(); d.mark("db"); receipt=x.admit_receipt("x",0,0); assert receipt.accepted(); assert receipt.request_id=="x"; x.release()

def test_coordinator_outcomes_drive_circuit_recovery():
 x,s,d=make(threshold=2); s.ready(); d.mark("db"); x.record_outcome(False); assert x.circuit.allowed; x.record_outcome(False); assert not x.circuit.allowed; assert not x.record_outcome(False); assert not x.circuit.allowed; x.circuit.probe(); assert x.record_outcome(True); assert x.circuit.allowed

def test_coordinator_preserves_read_only_path():
 x,s,d=make(); s.ready(); d.mark("db"); assert x.admit(0,0,request_id="ro",read_only=True) is Admission.READ_ONLY
