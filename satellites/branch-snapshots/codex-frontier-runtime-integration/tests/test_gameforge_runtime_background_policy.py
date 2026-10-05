from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_runtime_contract import RuntimeContract


def ready_contract(*, background_allowed=True):
    lifecycle = ServiceLifecycle()
    lifecycle.ready()
    deps = DependencyGate(["db"])
    deps.mark("db")
    return RuntimeContract(lifecycle, deps, background_allowed=background_allowed)


def test_background_work_is_shed_when_policy_disallows_it():
    contract = ready_contract(background_allowed=False)
    receipt = contract.admit("r1", background=True)
    assert receipt.decision == "shed"


def test_background_work_is_admitted_when_policy_allows_it():
    contract = ready_contract(background_allowed=True)
    receipt = contract.admit("r1", background=True)
    assert receipt.decision != "shed"


def test_runtime_flags_are_type_checked():
    contract = ready_contract()
    receipt = contract.admit("r1", background=1)  # type: ignore[arg-type]
    assert receipt.reason == "invalid_flags"
