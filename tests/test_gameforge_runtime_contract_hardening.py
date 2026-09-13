from skeleton.frontier.gameforge_admission import Admission
from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_runtime_contract import RuntimeContract


def ready_contract():
    lifecycle = ServiceLifecycle()
    lifecycle.ready()
    return RuntimeContract(lifecycle, DependencyGate())


def test_contract_rejects_missing_request_id():
    receipt = ready_contract().admit("")
    assert receipt.reason == "missing_request_id"
    assert receipt.decision == Admission.SHED.value


def test_contract_rejects_non_integer_limits():
    receipt = ready_contract().admit("r1", active=0.5)
    assert receipt.reason == "invalid_limits"
