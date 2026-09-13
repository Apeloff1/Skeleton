"""Tenant-aware execution broker joining ingress policy to runtime lifecycle."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock

from skeleton.agents.swarm_broker import CompletionResult, SwarmBroker
from skeleton.agents.swarm_ingress import IngressDecision, SwarmIngressGovernor
from skeleton.agents.swarm_runtime import AdmissionError, SwarmTask, TaskState


@dataclass(frozen=True, slots=True)
class TenantBrokerResult:
    tenant: str
    task_id: str
    admitted: bool
    duplicate: bool
    worker_id: str | None
    leased: bool
    reason: str


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

    def _remember_terminal(self, task_id: str, tenant: str) -> None:
        self._terminal_tenants[task_id] = tenant
        self._terminal_tenants.move_to_end(task_id)
        while len(self._terminal_tenants) > self.max_terminal_records:
            self._terminal_tenants.popitem(last=False)

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
            existing_tenant = self._tenant_by_task.get(task_id) or self._terminal_tenants.get(task_id)
            if existing_tenant is not None:
                if existing_tenant != tenant:
                    raise AdmissionError(f"task already belongs to tenant: {existing_tenant}")
                result = self.broker.submit_and_dispatch(task, idempotency_key=idempotency_key)
                return TenantBrokerResult(
                    tenant,
                    result.task_id,
                    True,
                    result.duplicate,
                    result.worker_id,
                    result.leased,
                    result.reason,
                )

            decision: IngressDecision = self.ingress.admit(tenant, task_id, task.payload, cost=cost)
            if not decision.accepted:
                return TenantBrokerResult(tenant, task_id, False, False, None, False, decision.reason)

            self._tenant_by_task[task_id] = tenant
            try:
                result = self.broker.submit_and_dispatch(task, idempotency_key=idempotency_key)
            except Exception:
                self.ingress.complete(tenant, task_id)
                self._tenant_by_task.pop(task_id, None)
                raise

            if result.leased:
                self.ingress.mark_leased(tenant, task_id)
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
            tenant = self._tenant_by_task.get(task_id) or self._terminal_tenants.get(task_id)
            if tenant is None:
                raise AdmissionError(f"task has no tenant accounting: {task_id}")
            result = self.broker.record_success(worker_id, task_id, completion_token=completion_token)
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
            elif result.task.state in {TaskState.SUCCEEDED, TaskState.DEAD, TaskState.CANCELLED, TaskState.FAILED}:
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
                "ingress": self.ingress.status(),
            }
