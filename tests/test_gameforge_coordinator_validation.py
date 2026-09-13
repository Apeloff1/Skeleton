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
    dependencies = DependencyGate(["db"])
    dependencies.mark("db")
    return RuntimeCoordinator(
        lifecycle, dependencies, RateWindow(10, 100), Circuit(3, 1.0),
        Budget(4), Quota(4), BoundedQueue(4), RetryBudget(4), HealthScore(),
    )


def test_admit_rejects_boolean_numeric_inputs():
    runtime = coordinator()
    with pytest.raises(TypeError):
        runtime.admit(True, 0)
    with pytest.raises(TypeError):
        runtime.admit(1, False)


def test_admit_rejects_invalid_limits():
    runtime = coordinator()
    with pytest.raises(ValueError):
        runtime.admit(1, 0, 0)
    with pytest.raises(ValueError):
        runtime.admit(1, -1)


def test_admit_rejects_non_boolean_flags():
    runtime = coordinator()
    with pytest.raises(TypeError):
        runtime.admit(1, 0, background=1)
    with pytest.raises(TypeError):
        runtime.admit(1, 0, retry=0)
    with pytest.raises(TypeError):
        runtime.admit(1, 0, read_only=None)


def test_snapshot_rejects_boolean_active_count():
    runtime = coordinator()
    with pytest.raises(ValueError):
        runtime.snapshot(True)
