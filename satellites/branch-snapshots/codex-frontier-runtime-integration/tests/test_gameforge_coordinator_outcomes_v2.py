from skeleton.frontier.gameforge_outcome_v2 import ExecutionOutcomeV2
from skeleton.frontier.gameforge_coordinator import RuntimeCoordinator
from skeleton.frontier.gameforge_admission import Admission
from skeleton.frontier.gameforge_budget import Budget
from skeleton.frontier.gameforge_circuit import Circuit
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
    return RuntimeCoordinator(lifecycle, _ready_dependencies(), RateWindow(4), Circuit(2),
                              Budget(2), Quota(2), BoundedQueue(2), RetryBudget(2), HealthScore(4))


def test_terminal_failure_trips_circuit_but_nonterminal_does_not():
    runtime = coordinator()
    assert not runtime.record_outcome(ExecutionOutcomeV2("r1", False, terminal=False))
    assert runtime.circuit.allowed
    runtime.record_outcome(ExecutionOutcomeV2("r1", False, terminal=True))
    runtime.record_outcome(ExecutionOutcomeV2("r2", False, terminal=True))
    assert not runtime.circuit.allowed


def test_saturated_reports_any_bounded_resource():
    runtime = coordinator()
    assert runtime.admit(0, 0, request_id="r1") is Admission.ACCEPT
    assert runtime.admit(1, 0, request_id="r2") is Admission.ACCEPT
    assert runtime.saturated


def _ready_dependencies():
    dependencies = DependencyGate(["core"])
    dependencies.mark("core")
    return dependencies
