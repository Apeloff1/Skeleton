"""Concurrency checks for recovered in-process coordinator ownership."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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


def make_coordinator():
    lifecycle = ServiceLifecycle()
    lifecycle.ready()
    dependencies = DependencyGate(["core"])
    dependencies.mark("core")
    return RuntimeCoordinator(
        lifecycle, dependencies, RateWindow(64), Circuit(), Budget(8),
        Quota(8), BoundedQueue(8), RetryBudget(8), HealthScore(),
    )


def test_concurrent_duplicate_admissions_and_releases_are_atomic():
    runtime = make_coordinator()
    barrier = Barrier(8)

    def admit(_):
        barrier.wait(timeout=5)
        return runtime.admit(0, 0, limit=8, request_id="shared")

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(admit, range(8)))
    assert outcomes.count(Admission.ACCEPT) == 1
    assert runtime.reservations == runtime.budget.used == runtime.quota.used == 1
    assert runtime.owned_request_ids == frozenset({"shared"})
    barrier = Barrier(8)

    def release(_):
        barrier.wait(timeout=5)
        return runtime.release("shared")

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(release, range(8)))
    assert outcomes.count(True) == 1
    assert runtime.reservations == runtime.budget.used == runtime.quota.used == 0
    assert not runtime.owned_request_ids
