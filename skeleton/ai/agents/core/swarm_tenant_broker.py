"""Tenant-aware execution broker joining ingress policy to runtime lifecycle."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock

from skeleton.agents.swarm_broker import CompletionResult, SwarmBroker
from skeleton.agents.swarm_ingress import IngressDecision, SwarmIngressGovernor
from skeleton.agents.swarm_lease_rollback import rollback_exact_lease
from skeleton.agents.swarm_runtime import AdmissionError, SwarmTask, TaskState

TERMINAL_STATES = {TaskState.SUCCEEDED, TaskState.DEAD, TaskState.CANCELLED, TaskState.FAILED}


@dataclass(frozen=True, slots=True)
class TenantBrokerResult:
    tenant: str
    task_id: str
    admitted: bool
    duplicate: bool
    worker_id: str | None
    leased: bool
    reason: str


@dataclass(frozen=True, slots=True)
class TenantRepairResult:
    removed_orphans: int
    restored_accounting: int
    phase_repairs: int
    terminalized: int
    reactivated: int


class TenantSwarmBroker:
    """Keeps tenant policy accounting synchronized with broker/runtime transitions."""

    def __init__(
        self,
        broker: SwarmBroker,
        ingress: SwarmIngressGovernor | None = None,
        *,
        max_terminal_records: int = 100_000,
    ) -> None:
        if max_terminal_records < 1:
            raise ValueError("max_terminal_records must be positive")
        self.broker = broker
        self.ingress = ingress or SwarmIngressGovernor()
        self.max_terminal_records = max_terminal_records
        self._tenant_by_task: dict[str, str] = {}
        self._terminal_tenants: OrderedDict[str, str] = OrderedDict()
        self._retired = False
        self._lock = RLock()

    @staticmethod
    def _tenant(tenant: str) -> str:
        tenant = tenant.strip()
        if not tenant:
            raise ValueError("tenant must not be empty")
        return tenant

    @staticmethod
    def _task_id(task_id: str) -> str:
        task_id = task_id.strip()
        if not task_id:
            raise ValueError("task_id must not be empty")
        return task_id

    def _assert_active(self) -> None:
        if self._retired:
            raise AdmissionError("tenant broker generation retired")

    def retire(self) -> bool:
        """Fence this broker generation so queued callers cannot mutate detached state."""
        with self._lock:
            if self._retired:
                return False
            self._retired = True
            return True

    def is_retired(self) -> bool:
        with self._lock:
            return self._retired

    def _remember_terminal(self, task_id: str, tenant: str) -> None:
        self._terminal_tenants[task_id] = tenant
        self._terminal_tenants.move_to_end(task_id)
        while len(self._terminal_tenants) > self.max_terminal_records:
            self._terminal_tenants.popitem(last=False)

    def _terminal_duplicate(self, task_id: str) -> CompletionResult | None:
        if task_id not in self._terminal_tenants:
            return None
        resident = self.broker.runtime.task(task_id)
        if resident is None or resident.state not in TERMINAL_STATES:
            return None
        self._terminal_tenants.move_to_end(task_id)
        return CompletionResult(resident, True)

    def rebind(self, broker: SwarmBroker) -> None:
        with self._lock:
            self._assert_active()
            self.broker = broker

    @staticmethod
    def _expected_phase(task: SwarmTask) -> str:
        return "leased" if task.state is TaskState.LEASED else "queued"

    def _repair_phase(self, tenant: str, task: SwarmTask) -> tuple[int, int]:
        expected = self._expected_phase(task)
        phase = self.ingress.phase(tenant, task.id)
        if phase is None:
            self.ingress.restore_task(tenant, task.id, task.payload, phase=expected)
            return 1, 0
        if phase == expected:
            return 0, 0
        if expected == "leased":
            self.ingress.mark_leased(tenant, task.id)
        else:
            self.ingress.mark_requeued(tenant, task.id)
        return 0, 1

    def reconcile(self) -> dict[str, tuple[str, ...]]:
        with self._lock:
            resident = {task.id: task for task in self.broker.runtime.tasks()}
            missing_active = tuple(
                sorted(task_id for task_id in self._tenant_by_task if task_id not in resident)
            )
            terminal_not_terminal = tuple(
                sorted(
                    task_id
                    for task_id in self._terminal_tenants
                    if task_id in resident and resident[task_id].state not in TERMINAL_STATES
                )
            )
            active_terminal = tuple(
                sorted(
                    task_id
                    for task_id in self._tenant_by_task
                    if task_id in resident and resident[task_id].state in TERMINAL_STATES
                )
            )
            phase_mismatch: list[str] = []
            for task_id, tenant in self._tenant_by_task.items():
                task = resident.get(task_id)
                if task is None or task.state in TERMINAL_STATES:
                    continue
                if self.ingress.phase(tenant, task_id) != self._expected_phase(task):
                    phase_mismatch.append(task_id)
            return {
                "missing_active": missing_active,
                "terminal_not_terminal": terminal_not_terminal,
                "active_terminal": active_terminal,
                "phase_mismatch": tuple(sorted(phase_mismatch)),
            }

    def repair(self) -> TenantRepairResult:
        """Reconcile tenant metadata/accounting against the live runtime as authority."""
        with self._lock:
            self._assert_active()
            resident = {task.id: task for task in self.broker.runtime.tasks()}
            removed_orphans = restored_accounting = phase_repairs = terminalized = reactivated = 0

            for task_id, tenant in list(self._tenant_by_task.items()):
                task = resident.get(task_id)
                phase = self.ingress.phase(tenant, task_id)
                if task is None:
                    if phase is not None:
                        self.ingress.complete(tenant, task_id)
                    self._tenant_by_task.pop(task_id, None)
                    removed_orphans += 1
                    continue
                if task.state in TERMINAL_STATES:
                    if phase is not None:
                        self.ingress.complete(tenant, task_id)
                    self._tenant_by_task.pop(task_id, None)
                    self._remember_terminal(task_id, tenant)
                    terminalized += 1
                    continue
                restored, repaired = self._repair_phase(tenant, task)
                restored_accounting += restored
                phase_repairs += repaired

            for task_id, tenant in list(self._terminal_tenants.items()):
                task = resident.get(task_id)
                if task is None or task.state in TERMINAL_STATES:
                    continue
                self._terminal_tenants.pop(task_id, None)
                self._tenant_by_task[task_id] = tenant
                restored, repaired = self._repair_phase(tenant, task)
                restored_accounting += restored
                phase_repairs += repaired
                reactivated += 1

            return TenantRepairResult(
                removed_orphans,
                restored_accounting,
                phase_repairs,
                terminalized,
                reactivated,
            )

    def tenant_for(self, task_id: str) -> str | None:
        task_id = self._task_id(task_id)
        with self._lock:
            return self._tenant_by_task.get(task_id) or self._terminal_tenants.get(task_id)

    def submit_and_dispatch(
        self,
        tenant: str,
        task: SwarmTask,
        *,
        idempotency_key: str | None = None,
        cost: float = 1.0,
    ) -> TenantBrokerResult:
        tenant = self._tenant(tenant)
        task_id = self._task_id(task.id)
        with self._lock:
            self._assert_active()
            active_tenant = self._tenant_by_task.get(task_id)
            if active_tenant is not None:
                if active_tenant != tenant:
                    raise AdmissionError(f"task already belongs to tenant: {active_tenant}")
                resident = self.broker.runtime.task(task_id)
                if resident is None:
                    raise AdmissionError(
                        f"active tenant task missing from runtime: {task_id}; repair required"
                    )
                if resident.state in TERMINAL_STATES:
                    raise AdmissionError(
                        f"active tenant task is terminal: {task_id}; repair required"
                    )
                return TenantBrokerResult(
                    tenant,
                    task_id,
                    True,
                    True,
                    resident.leased_to,
                    resident.state is TaskState.LEASED,
                    f"active task already accounted in state {resident.state.value}",
                )

            terminal_tenant = self._terminal_tenants.get(task_id)
            if terminal_tenant is not None:
                if terminal_tenant != tenant:
                    raise AdmissionError(f"task already belongs to tenant: {terminal_tenant}")
                resident = self.broker.runtime.task(task_id)
                if resident is not None and resident.state not in TERMINAL_STATES:
                    raise AdmissionError(
                        f"terminal tenant task is active: {task_id}; repair required"
                    )
                self._terminal_tenants.move_to_end(task_id)
                return TenantBrokerResult(
                    tenant,
                    task_id,
                    True,
                    True,
                    None,
                    False,
                    "terminal task already accounted",
                )

            decision: IngressDecision = self.ingress.admit(
                tenant,
                task_id,
                task.payload,
                cost=cost,
            )
            if not decision.accepted:
                return TenantBrokerResult(
                    tenant,
                    task_id,
                    False,
                    False,
                    None,
                    False,
                    decision.reason,
                )

            self._tenant_by_task[task_id] = tenant
            try:
                result = self.broker.submit_and_dispatch(task, idempotency_key=idempotency_key)
            except Exception:
                self.ingress.complete(tenant, task_id)
                self._tenant_by_task.pop(task_id, None)
                raise

            if result.leased:
                try:
                    self.ingress.mark_leased(tenant, task_id)
                except Exception as exc:
                    if result.worker_id is None:
                        raise RuntimeError(
                            f"leased task missing worker identity: {task_id}"
                        ) from exc
                    try:
                        rollback_exact_lease(self.broker.runtime, result.worker_id, task_id)
                    except Exception as rollback_exc:
                        raise RuntimeError(
                            f"lease accounting rejected and runtime rollback failed: {task_id}"
                        ) from rollback_exc
                    return TenantBrokerResult(
                        tenant,
                        task_id,
                        True,
                        result.duplicate,
                        None,
                        False,
                        f"lease accounting rejected: {exc}",
                    )

            return TenantBrokerResult(
                tenant,
                result.task_id,
                True,
                result.duplicate,
                result.worker_id,
                result.leased,
                result.reason,
            )

    def record_success(
        self,
        worker_id: str,
        task_id: str,
        *,
        completion_token: str | None = None,
    ) -> CompletionResult:
        task_id = self._task_id(task_id)
        with self._lock:
            self._assert_active()
            duplicate = self._terminal_duplicate(task_id)
            if duplicate is not None:
                return duplicate
            tenant = self._tenant_by_task.get(task_id) or self._terminal_tenants.get(task_id)
            if tenant is None:
                raise AdmissionError(f"task has no tenant accounting: {task_id}")
            result = self.broker.record_success(
                worker_id,
                task_id,
                completion_token=completion_token,
            )
            if not result.duplicate and task_id in self._tenant_by_task:
                self.ingress.complete(tenant, task_id)
                self._tenant_by_task.pop(task_id, None)
                self._remember_terminal(task_id, tenant)
            return result

    def record_failure(
        self,
        worker_id: str,
        task_id: str,
        error: str,
        *,
        completion_token: str | None = None,
    ) -> CompletionResult:
        task_id = self._task_id(task_id)
        with self._lock:
            self._assert_active()
            duplicate = self._terminal_duplicate(task_id)
            if duplicate is not None:
                return duplicate
            tenant = self._tenant_by_task.get(task_id) or self._terminal_tenants.get(task_id)
            if tenant is None:
                raise AdmissionError(f"task has no tenant accounting: {task_id}")
            result = self.broker.record_failure(
                worker_id,
                task_id,
                error,
                completion_token=completion_token,
            )
            if result.duplicate:
                return result
            if result.task.state is TaskState.QUEUED:
                self.ingress.mark_requeued(tenant, task_id)
            elif result.task.state in TERMINAL_STATES:
                if task_id in self._tenant_by_task:
                    self.ingress.complete(tenant, task_id)
                    self._tenant_by_task.pop(task_id, None)
                self._remember_terminal(task_id, tenant)
            return result

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "tenants_by_task": dict(sorted(self._tenant_by_task.items())),
                "terminal_tenants": dict(self._terminal_tenants),
                "tracked_tasks": len(self._tenant_by_task),
                "terminal_records": len(self._terminal_tenants),
                "retired": self._retired,
                "reconcile": self.reconcile(),
                "ingress": self.ingress.status(),
            }
