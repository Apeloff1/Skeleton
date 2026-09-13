from skeleton.frontier.gameforge_admission import Admission
from skeleton.frontier.gameforge_budget import Budget
from skeleton.frontier.gameforge_circuit import Circuit
from skeleton.frontier.gameforge_coordinator import RuntimeCoordinator
from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_quota import Quota
from skeleton.frontier.gameforge_queue import BoundedQueue
from skeleton.frontier.gameforge_rate import RateWindow

def make(queue_capacity=1):
 s=ServiceLifecycle(); d=DependencyGate(("db",)); r=RateWindow(2,10); c=Circuit(2); b=Budget(1); q=Quota(1); queue=BoundedQueue(queue_capacity); return RuntimeCoordinator(s,d,r,c,b,q,queue),s,d

def test_coordinator_fails_closed_until_ready():
 x,s,d=make(); assert x.admit(0,0,"x") is Admission.SHED; s.ready(); d.mark("db"); assert x.admit(0,0,request_id="x") is Admission.ACCEPT

def test_coordinator_composes_budget_and_rate():
 x,s,d=make(); s.ready(); d.mark("db"); assert x.admit(0,0,request_id="x") is Admission.ACCEPT; assert x.admit(1,0,request_id="y") is Admission.SHED; x.release(); assert x.admit(1,0,request_id="z") is Admission.ACCEPT

def test_coordinator_quota_rejects_without_leaking_budget():
 x,s,d=make(); x.quota.limit=0; s.ready(); d.mark("db"); assert x.admit(0,0,request_id="x") is Admission.SHED; assert x.budget.used==0

def test_coordinator_queue_rejects_without_leaking_reservations():
 x,s,d=make(0); s.ready(); d.mark("db"); assert x.admit(0,0,request_id="x") is Admission.SHED; assert x.budget.used==0; assert x.quota.used==0
