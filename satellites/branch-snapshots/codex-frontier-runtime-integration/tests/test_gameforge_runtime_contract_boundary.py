import pytest

from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_runtime_contract import RuntimeContract


def ready_contract():
    lifecycle = ServiceLifecycle()
    lifecycle.ready()
    deps = DependencyGate(["db"])
    deps.mark("db")
    return RuntimeContract(lifecycle, deps)


def test_runtime_contract_rejects_boolean_limits():
    contract = ready_contract()
    receipt = contract.admit("r1", active=True)
    assert receipt.decision == "shed"
    assert receipt.reason == "invalid_limits"


def test_runtime_contract_rejects_non_string_request_ids():
    contract = ready_contract()
    receipt = contract.admit(123)
    assert receipt.decision == "shed"
    assert receipt.request_id == "invalid-request"


def test_runtime_contract_version_rejects_bool():
    lifecycle = ServiceLifecycle()
    deps = _ready_dependencies()
    with pytest.raises(ValueError):
        RuntimeContract(lifecycle, deps, version=True)


def _ready_dependencies():
    dependencies = DependencyGate(["core"])
    dependencies.mark("core")
    return dependencies
