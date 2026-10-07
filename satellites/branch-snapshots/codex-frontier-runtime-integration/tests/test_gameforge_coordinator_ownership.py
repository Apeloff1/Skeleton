import pytest

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


def coordinator():
    lifecycle = ServiceLifecycle()
    lifecycle.ready()
    deps = DependencyGate(["core"])
    deps.mark("core")
    return RuntimeCoordinator(lifecycle, deps, RateWindow(10), Circuit(), Budget(4),
                              Quota(4), BoundedQueue(4), RetryBudget(4), HealthScore())


def test_duplicate_request_id_does_not_double_reserve():
    runtime = coordinator()
    assert runtime.admit(0, 0, request_id="a") is Admission.ACCEPT
    assert runtime.admit(1, 0, request_id="a") is Admission.SHED
    assert runtime.reservations == 1
    assert runtime.owned_request_ids == frozenset({"a"})
    assert runtime.budget.used == 1


def test_release_targets_exact_request():
    runtime = coordinator()
    assert runtime.admit(0, 0, request_id="a") is Admission.ACCEPT
    assert runtime.admit(1, 0, request_id="b") is Admission.ACCEPT
    assert not runtime.release("missing")
    assert runtime.reservations == 2
    assert runtime.release("b")
    assert runtime.owned_request_ids == frozenset({"a"})
    assert runtime.reservations == 1
    assert runtime.release("a")
    assert runtime.reservations == 0


def test_admit_receipt_requires_non_empty_request_id():
    runtime = coordinator()
    with pytest.raises(ValueError):
        runtime.admit_receipt(" ", 0, 0)
