from skeleton.frontier.gameforge_admission import Admission
from skeleton.frontier.gameforge_budget import Budget
from skeleton.frontier.gameforge_circuit import Circuit
from skeleton.frontier.gameforge_coordinator import RuntimeCoordinator
from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_rate import RateWindow

def make():
 s=ServiceLifecycle(); d=DependencyGate(("db",)); r=RateWindow(2,10); c=Circuit(2); b=Budget(1); return RuntimeCoordinator(s,d,r,c,b),s,d

def test_coordinator_fails_closed_until_ready():
 x,s,d=make(); assert x.admit(0,0) is Admission.SHED; s.ready(); d.mark("db"); assert x.admit(0,0) is Admission.ACCEPT

def test_coordinator_composes_budget_and_rate():
 x,s,d=make(); s.ready(); d.mark("db"); assert x.admit(0,0) is Admission.ACCEPT; assert x.admit(1,0) is Admission.SHED; x.release(); assert x.admit(1,0) is Admission.ACCEPT
