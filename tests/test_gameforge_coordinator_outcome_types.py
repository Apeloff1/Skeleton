import pytest

from skeleton.frontier.gameforge_budget import Budget
from skeleton.frontier.gameforge_circuit import Circuit
from skeleton.frontier.gameforge_coordinator import RuntimeCoordinator
from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_health_score import HealthScore
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_queue import BoundedQueue
from skeleton.frontier.gameforge_rate import RateWindow
from skeleton.frontier.gameforge_retry_budget import RetryBudget
from skeleton.frontier.gameforge_quota import Quota


def coordinator():
    lifecycle = ServiceLifecycle()
    lifecycle.ready()
    return RuntimeCoordinator(lifecycle, DependencyGate([]), RateWindow(4), Circuit(), Budget(2),
                              Quota(2), BoundedQueue(2), RetryBudget(2), HealthScore())


def test_coordinator_rejects_non_boolean_raw_outcome():
    with pytest.raises(TypeError):
        coordinator().record_outcome(1)


def test_coordinator_accepts_boolean_raw_outcome():
    assert coordinator().record_outcome(True)
