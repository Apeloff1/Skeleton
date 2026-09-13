from skeleton.frontier.gameforge_admission import Admission
from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_runtime_contract import RuntimeContract

def test_runtime_contract_returns_observable_receipt():
 s=ServiceLifecycle(); d=DependencyGate(("core",)); r=RuntimeContract(s,d); assert r.admit("r1").decision==Admission.SHED.value; s.ready(); d.mark("core"); assert r.admit("r1").accepted()

def test_runtime_contract_preserves_read_only():
 s=ServiceLifecycle(); d=DependencyGate(("core",)); r=RuntimeContract(s,d); s.ready(); d.mark("core"); assert r.admit("r1",read_only=True).decision==Admission.READ_ONLY.value
