from skeleton.frontier.gameforge_admission import Admission
from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_runtime_contract import RuntimeContract

def test_runtime_contract_composes_readiness_and_admission():
 s=ServiceLifecycle(); d=DependencyGate(("core",)); r=RuntimeContract(s,d); assert r.admit() is Admission.SHED; s.ready(); assert r.admit() is Admission.SHED; d.mark("core"); assert r.admit() is Admission.ACCEPT

def test_runtime_contract_can_enter_read_only():
 s=ServiceLifecycle(); d=DependencyGate(("core",)); r=RuntimeContract(s,d); s.ready(); d.mark("core"); assert r.admit(read_only=True) is Admission.READ_ONLY
