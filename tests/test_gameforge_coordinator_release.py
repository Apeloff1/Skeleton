from skeleton.frontier.gameforge_coordinator import RuntimeCoordinator
from skeleton.frontier.gameforge_lifecycle import ServiceLifecycle
from skeleton.frontier.gameforge_dependency import DependencyGate
from skeleton.frontier.gameforge_rate import RateWindow
from skeleton.frontier.gameforge_circuit import Circuit
from skeleton.frontier.gameforge_budget import Budget
from skeleton.frontier.gameforge_quota import Quota
from skeleton.frontier.gameforge_queue import BoundedQueue
from skeleton.frontier.gameforge_retry_budget import RetryBudget
from skeleton.frontier.gameforge_health_score import HealthScore


def coordinator():
    lifecycle = ServiceLifecycle()
    lifecycle.ready()
    return RuntimeCoordinator(lifecycle, DependencyGate(), RateWindow(8), Circuit(),
                              Budget(2), Quota(2), BoundedQueue(2), RetryBudget(2), HealthScore())


def test_release_without_reservation_is_noop():
    c = coordinator()
    assert c.release() is False
    assert c.reservations == 0


def test_release_reverses_one_reservation():
    c = coordinator()
    assert c.admit(1, 0).value == "accept"
    assert c.reservations == 1
    assert c.release() is True
    assert c.reservations == 0
    assert c.budget.used == 0
    assert c.quota.used == 0
