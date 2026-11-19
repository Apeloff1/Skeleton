import pytest

from skeleton.frontier.gameforge_admission import Admission
from skeleton.frontier.gameforge_budget import Budget
from skeleton.frontier.gameforge_circuit import Circuit
from skeleton.frontier.gameforge_coordinator import RuntimeCoordinator
from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_health_score import HealthScore
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_queue import BoundedQueue
from skeleton.frontier.gameforge_quota import Quota
from skeleton.frontier.gameforge_rate import RateWindow
from skeleton.frontier.gameforge_retry_budget import RetryBudget


def coordinator():
    lifecycle = ServiceLifecycle()
    lifecycle.ready()
    dependencies = DependencyGate(["core"])
    dependencies.mark("core")
    return RuntimeCoordinator(
        lifecycle, dependencies, RateWindow(10), Circuit(), Budget(4), Quota(4),
        BoundedQueue(4), RetryBudget(2), HealthScore(),
    )


def test_admit_rejects_empty_request_id():
    with pytest.raises(ValueError):
        coordinator().admit(0, 0, request_id=" ")


def test_admit_rejects_unhashable_request_id():
    with pytest.raises(ValueError):
        coordinator().admit(0, 0, request_id=[])


def test_release_rejects_invalid_request_id():
    with pytest.raises(ValueError):
        coordinator().release([])


def test_valid_request_id_remains_owned_until_release():
    runtime = coordinator()
    assert runtime.admit(0, 0, request_id="r1") is Admission.ACCEPT
    assert runtime.owned_request_ids == frozenset({"r1"})
    assert runtime.release("r1")
    assert not runtime.owned_request_ids
