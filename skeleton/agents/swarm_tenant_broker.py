"""Tenant-aware execution broker joining ingress policy to runtime lifecycle."""

from __future__ import annotations

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
    ) -> None:
        self.broker = broker
        self.ingress = ingress or SwarmIngressGovernor()
        self._tenant_by_task: dict[str, str] = {}
        self._lock = RLock()

    @staticmethod
    def _tenant(tenant: str) -> str:
        tenant = tenant.strip()
        if not tenant:
            raise ValueError("tenant must not be empty")
        return tenant

    def tenant_for(self, task_id: str) -> str | None:
        with self._lock:
            return self._tenant_by_task.get(task_id.strip())

    def submit_and_dispatch(
        self,
        tenant: str,
        task: SwarmTask,
        *,
        idempotency_key: str | None = None,
        cost: float = 1.0,
    ) -> TenantBrokerResult:
        tenant = self._tenant(tenant)
        with self._lock:
            existing_tenant = self._tenant_by_task.get(task.id)
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

            decision: IngressDecision = self.ingress.admit(tenant, task.id, task.payload, cost=cost)
            if not decision.accepted:
                return TenantBrokerResult(tenant, task.id, False, False, None, False, decision.reason)

            self._tenant_by_task[task.id] = tenant
            try:
                result = self.broker.submit_and_dispatch(task, idempotency_key=idempotency_key)
            except Exception:
                self.ingress.complete(tenant, task.id)
                self._tenant_by_task.pop(task.id, None)
                raise

            if result.leased:
                self.ingress.mark_leased(tenant, task.id)
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
        with self._lock:
            tenant = self._tenant_by_task.get(task_id)
            if tenant is None:
                raise AdmissionError(f"task has no tenant accounting: {task_id}")
            result = self.broker.record_success(worker_id, task_id, completion_token=completion_token)
            if not result.duplicate:
                self.ingress.complete(tenant, task_id)
                self._tenant_by_task.pop(task_id, None)
            return result

    def record_failure(
        self,
        worker_id: str,
        task_id: str,
        error: str,
        *,
        completion_token: str | None = None,
    ) -> CompletionResult:
        with self._lock:
            tenant = self._tenant_by_task.get(task_id)
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
                self.ingress.complete(tenant, task_id)
                self._tenant_by_task.pop(task_id, None)
            return result

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "tenants_by_task": dict(sorted(self._tenant_by_task.items())),
                "tracked_tasks": len(self._tenant_by_task),
                "ingress": self.ingress.status(),
            }
