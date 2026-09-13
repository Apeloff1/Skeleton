"""Runtime coordinator composing lifecycle, dependencies, rate, circuit, and bounded budgets."""
from dataclasses import dataclass
from .gameforge_admission import Admission, decide
from .gameforge_budget import Budget
from .gameforge_circuit import Circuit
from .gameforge_dependency import DependencyGate
from .gameforge_lifecycle import ServiceLifecycle
from .gameforge_rate import RateWindow
from .gameforge_quota import Quota
from .gameforge_queue import BoundedQueue
from .gameforge_retry_budget import RetryBudget
from .gameforge_health_score import HealthScore
from .gameforge_snapshot import RuntimeSnapshot
from .gameforge_receipt import Receipt
from .gameforge_outcome_v2 import ExecutionOutcomeV2


@dataclass
class RuntimeCoordinator:
    lifecycle: ServiceLifecycle
    dependencies: DependencyGate
    rate: RateWindow
    circuit: Circuit
    budget: Budget
    quota: Quota
    queue: BoundedQueue
    retry_budget: RetryBudget
    health: HealthScore

    def __post_init__(self):
        self._reservations = 0

    def admit(self, now: int, active: int, limit: int = 1, background: bool = False,
              request_id=None, retry: bool = False, read_only: bool = False):
        if retry and not self.retry_budget.consume():
            self.health.record(False)
            return Admission.SHED
        if not self.lifecycle.can_accept or not self.dependencies.ready or not self.circuit.allowed:
            self.health.record(False)
            return Admission.SHED
        if not self.rate.allow(now):
            self.health.record(False)
            return Admission.SHED
        decision = decide(background_allowed=True, read_only=read_only, active=active,
                          limit=limit, background=background)
        if decision is Admission.ACCEPT:
            if not self.budget.reserve():
                self.health.record(False)
                return Admission.SHED
            if not self.quota.reserve():
                self.budget.release()
                self.health.record(False)
                return Admission.SHED
            if not self.queue.push(request_id):
                self.quota.release()
                self.budget.release()
                self.health.record(False)
                return Admission.SHED
            self._reservations += 1
        self.health.record(decision is not Admission.SHED)
        return decision

    def admit_receipt(self, request_id, now: int, active: int, limit: int = 1,
                      background: bool = False, retry: bool = False, read_only: bool = False):
        decision = self.admit(now, active, limit, background, request_id, retry, read_only)
        return Receipt(request_id, decision.value, decision.value)

    def record_outcome(self, success: bool, request_id: str = ""):
        if isinstance(success, ExecutionOutcomeV2):
            outcome = success
        else:
            if not isinstance(success, bool):
                raise TypeError("success must be bool or ExecutionOutcomeV2")
            outcome = ExecutionOutcomeV2(request_id or "anonymous", success)
        self.health.record(outcome.success)
        if outcome.success:
            self.circuit.success()
        elif outcome.terminal:
            self.circuit.failure()
        return self.health.healthy

    @property
    def reservations(self):
        return self._reservations

    @property
    def saturated(self):
        return self.budget.exhausted or self.quota.exhausted or self.queue.full

    def release(self, request_id=None):
        """Release one reservation, optionally targeting its request identity."""
        if self._reservations <= 0:
            return False
        if request_id is not None and not self.queue.remove(request_id):
            return False
        if request_id is None:
            self.queue.pop()
        self.budget.release()
        self.quota.release()
        self._reservations -= 1
        return True

    def snapshot(self, active: int = 0):
        return RuntimeSnapshot(self.lifecycle.state.value, self.dependencies.ready, active,
                               self.budget.used, self.budget.capacity, self.quota.used,
                               len(self.queue), self.health.value)
