"""Tenant-aware execution broker joining ingress policy to runtime lifecycle."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from threading import RLock

from skeleton.automation.agents.swarm_broker import CompletionResult, SwarmBroker
from skeleton.automation.agents.swarm_ingress import IngressDecision, SwarmIngressGovernor
from skeleton.automation.agents.swarm_lease_rollback import rollback_exact_lease
from skeleton.automation.agents.swarm_runtime import AdmissionError, LeaseError, SwarmTask, TaskState
from skeleton.automation.agents.swarm_quota import QuotaExceeded

TERMINAL_STATES = {TaskState.SUCCEEDED, TaskState.DEAD, TaskState.CANCELLED, TaskState.FAILED}


def is_terminal(task: SwarmTask) -> bool:
    return task.state in TERMINAL_STATES and not task.effect_uncertain


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
        verified_mode: bool = False,
    ) -> None:
        if max_terminal_records < 1:
            raise ValueError("max_terminal_records must be positive")
        if type(verified_mode) is not bool or verified_mode != broker.runtime.fenced:
            raise AdmissionError("fenced tenant dispatch requires explicit verified host mode")
        self.verified_mode = verified_mode
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
            if self.verified_mode:
                raise AdmissionError("verified terminal identity capacity exhausted")
            self._terminal_tenants.popitem(last=False)

    def _terminal_duplicate(self, task_id: str) -> CompletionResult | None:
        if task_id not in self._terminal_tenants:
            return None
        resident = self.broker.runtime.task(task_id)
        if resident is None or not is_terminal(resident):
            return None
        self._terminal_tenants.move_to_end(task_id)
        return CompletionResult(resident, True)

    def rebind(self, broker: SwarmBroker) -> None:
        with self._lock:
            self._assert_active()
            if self.verified_mode or broker.runtime.fenced:
                raise AdmissionError("verified rebinding requires explicit checkpoint recovery")
            self.broker = broker

    @staticmethod
    def _expected_phase(task: SwarmTask) -> str:
        return "leased" if task.state is TaskState.LEASED or task.effect_uncertain else "queued"

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
                    if task_id in resident and not is_terminal(resident[task_id])
                )
            )
            active_terminal = tuple(
                sorted(
                    task_id
                    for task_id in self._tenant_by_task
                    if task_id in resident and is_terminal(resident[task_id])
                )
            )
            phase_mismatch: list[str] = []
            for task_id, tenant in self._tenant_by_task.items():
                task = resident.get(task_id)
                if task is None or is_terminal(task):
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
                    if self.verified_mode:
                        raise AdmissionError("verified task custody is missing; retain accounting")
                    if phase is not None:
                        self.ingress.complete(tenant, task_id)
                    self._tenant_by_task.pop(task_id, None)
                    removed_orphans += 1
                    continue
                if is_terminal(task):
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
                if task is None or is_terminal(task):
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

    def _assert_verified(self) -> None:
        self._assert_active()
        if not self.verified_mode:
            raise AdmissionError("verified tenant dispatch is not enabled")

    def _verified_resident(self, tenant: str, task_id: str) -> SwarmTask:
        self._assert_verified()
        if self._tenant_by_task.get(task_id) != tenant:
            raise AdmissionError("task is not owned by the active tenant")
        task = self.broker.runtime.task(task_id)
        if task is None:
            raise AdmissionError("verified resident custody missing")
        return task

    @staticmethod
    def _same_submission(left: SwarmTask, right: SwarmTask) -> bool:
        return (left.id == right.id and left.payload == right.payload
                and left.priority == right.priority and left.max_attempts == right.max_attempts
                and left.required_capabilities == right.required_capabilities
                and left.dependencies == right.dependencies
                and left.wait_intent_sha256 == right.wait_intent_sha256
                and left.singleton_scope_sha256 == right.singleton_scope_sha256)

    def submit_verified_queued(self, tenant: str, task: SwarmTask, *, cost: float = 1.0,
                               singleton_key: str | None = None) -> TenantBrokerResult:
        """Admit a host-authorized task without dispatching it.

        Owner-supplied tenant, task and cost are trusted host inputs, not
        authorization inferred from model output. Every dependency stays in
        the same tenant. Terminal identity retention reserves capacity at
        admission, so verified tasks never silently evict replay tombstones.
        """
        tenant, task_id = self._tenant(tenant), self._task_id(task.id)
        if task.wake_receipt_sha256 is not None:
            raise AdmissionError("submission cannot assert its own wake receipt")
        scope = None
        if singleton_key is not None:
            if (type(singleton_key) is not str or not singleton_key or len(singleton_key) > 256
                    or singleton_key != singleton_key.strip() or any(ord(c) < 32 for c in singleton_key)):
                raise AdmissionError("invalid singleton key")
            scope = sha256(json.dumps(["singleton-v1", tenant, singleton_key],
                                      separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        if task.singleton_scope_sha256 not in (None, scope):
            raise AdmissionError("singleton scope is assigned by tenant owner")
        task = replace(task, singleton_scope_sha256=scope)
        if task.id != task_id:
            raise AdmissionError("verified task identifier must be canonical")
        runtime = self.broker.runtime
        with self._lock, runtime._lock:
            self._assert_verified()
            owner = self._tenant_by_task.get(task_id) or self._terminal_tenants.get(task_id)
            resident = runtime.task(task_id)
            if owner is not None:
                if owner != tenant or resident is None or not self._same_submission(resident, task):
                    raise AdmissionError("verified task identity conflict")
                return TenantBrokerResult(tenant, task_id, True, True, None, False, "known task")
            if resident is not None:
                raise AdmissionError("unaccounted resident task")
            if len(self._tenant_by_task) + len(self._terminal_tenants) >= self.max_terminal_records:
                raise AdmissionError("verified identity retention exhausted")
            for parent in task.dependencies:
                if (self._tenant_by_task.get(parent) or self._terminal_tenants.get(parent)) != tenant:
                    raise AdmissionError("dependency is not owned by tenant")
            decision = self.ingress.admit(tenant, task_id, task.payload, cost=cost)
            if not decision.accepted:
                return TenantBrokerResult(tenant, task_id, False, False, None, False, decision.reason)
            self._tenant_by_task[task_id] = tenant
            try:
                self.broker.submit_queued(task)
            except Exception:
                # Do not erase a reservation if publication may have succeeded.
                if runtime.task(task_id) is None:
                    self.ingress.complete(tenant, task_id)
                    self._tenant_by_task.pop(task_id, None)
                raise
            return TenantBrokerResult(tenant, task_id, True, False, None, False, "queued")

    def lease_verified(self, tenant: str, task_id: str) -> SwarmTask | None:
        """Reserve tenant quota before publishing an exact new attempt."""
        tenant, task_id = self._tenant(tenant), self._task_id(task_id)
        runtime = self.broker.runtime
        with self._lock, runtime._lock:
            task = self._verified_resident(tenant, task_id)
            if task.state is not TaskState.QUEUED or self.ingress.phase(tenant, task_id) != "queued":
                return None
            if runtime.dispatch_blocked(task_id) or not self.ingress.try_start(tenant):
                return None
            self.ingress.mark_leased(tenant, task_id)
            try:
                result = self.broker.lease_authorized(task_id)
            except Exception:
                current = runtime.task(task_id)
                if current is not None and current.state is TaskState.QUEUED and not current.effect_uncertain:
                    self.ingress.mark_requeued(tenant, task_id)
                raise
            if result is None:
                self.ingress.mark_requeued(tenant, task_id)
            return result

    def lease_ranked_verified(self, candidates: tuple, *, now_ms: int,
                              aging_interval_ms: int = 30_000) -> tuple[str, SwarmTask] | None:
        """Rank an explicitly host-authorized set, then lease through this owner.

        Scheduling observations cannot change an admitted task's tenant or
        priority. Every reservation uses existing tenant quota, supervisor
        health/capability checks, and exact runtime leasing. The caller must
        authenticate the supplied observation set before calling.
        """
        from skeleton.intelligence.dispatch_policy import DispatchCandidate, rank_candidates

        if type(candidates) is not tuple or len(candidates) > 4096:
            raise AdmissionError("invalid authorized dispatch candidate set")
        runtime = self.broker.runtime
        with self._lock, runtime._lock:
            self._assert_verified()
            seen: set[str] = set()
            active: dict[str, int] = {}
            eligible: list[DispatchCandidate] = []
            by_id: dict[str, DispatchCandidate] = {}
            for candidate in candidates:
                if not isinstance(candidate, DispatchCandidate) or candidate.ticket_id in seen:
                    raise AdmissionError("invalid or duplicate dispatch observation")
                seen.add(candidate.ticket_id)
                if self.tenant_for(candidate.ticket_id) != candidate.tenant_id:
                    raise AdmissionError("dispatch observation tenant mismatch")
                task = runtime.task(candidate.ticket_id)
                if task is None or task.priority != candidate.priority:
                    raise AdmissionError("dispatch observation identity mismatch")
                if task.state is not TaskState.QUEUED or runtime.dispatch_blocked(task.id):
                    continue
                if self.ingress.phase(candidate.tenant_id, task.id) != "queued":
                    raise AdmissionError("queued tenant quota missing")
                usage = self.ingress.quota.usage(candidate.tenant_id)
                if usage.leased >= self.ingress.quota.limit(candidate.tenant_id).max_leased:
                    continue
                active[candidate.tenant_id] = usage.leased
                by_id[task.id] = candidate
                eligible.append(candidate)
            configured = self.ingress.fairness.configured_weights()
            weights = {tenant: min(1000, configured.get(tenant, self.ingress.fairness.default_weight))
                       for tenant in active}
            for entry in rank_candidates(eligible, now_ms=now_ms, tenant_active=active,
                                         tenant_weights=weights, aging_interval_ms=aging_interval_ms):
                candidate = by_id[entry.ticket_id]
                try:
                    lease = self.lease_verified(candidate.tenant_id, candidate.ticket_id)
                except QuotaExceeded:
                    continue
                if lease is not None:
                    return candidate.tenant_id, lease
            return None

    def _sync_verified_outcome(self, tenant: str, task: SwarmTask) -> None:
        if task.effect_uncertain:
            # Unknown effects continue charging leased quota.
            return
        if is_terminal(task):
            self.ingress.complete(tenant, task.id)
            self._tenant_by_task.pop(task.id, None)
            self._remember_terminal(task.id, tenant)
        elif task.state is TaskState.QUEUED and self.ingress.phase(tenant, task.id) == "leased":
            self.ingress.mark_requeued(tenant, task.id)

    def record_verified(self, tenant: str, worker_id: str, task_id: str, *,
                        lease_token: str, outcome: str, evidence_sha256: str) -> CompletionResult:
        """Accept verified completion or hold; retry requires an explicit reconciliation."""
        tenant, task_id = self._tenant(tenant), self._task_id(task_id)
        if outcome not in {"success", "uncertain"}:
            raise LeaseError("verified tenant outcomes must be success or uncertain")
        runtime = self.broker.runtime
        with self._lock, self.broker._completion_lock, runtime._lock:
            self._verified_resident(tenant, task_id)
            if self.ingress.phase(tenant, task_id) != "leased":
                raise AdmissionError("leased quota custody missing")
            result = self.broker.record_verified(
                worker_id, task_id, lease_token=lease_token, outcome=outcome, evidence_sha256=evidence_sha256,
            )
            self._sync_verified_outcome(tenant, result.task)
            return result

    def reconcile_verified(self, tenant: str, worker_id: str, task_id: str, *,
                           lease_token: str, outcome: str, evidence_sha256: str) -> CompletionResult:
        """Reserve retry quota before allowing a stopped physical attempt to requeue."""
        tenant, task_id = self._tenant(tenant), self._task_id(task_id)
        runtime = self.broker.runtime
        with self._lock, self.broker._completion_lock, runtime._lock:
            task = self._verified_resident(tenant, task_id)
            if not task.effect_uncertain or self.ingress.phase(tenant, task_id) != "leased":
                raise AdmissionError("uncertain leased custody missing")
            retry = outcome == "stopped-no-effect" and task.attempts < task.max_attempts
            if retry:
                self.ingress.mark_requeued(tenant, task_id)
            try:
                result = self.broker.reconcile_verified(
                    worker_id, task_id, lease_token=lease_token, outcome=outcome,
                    evidence_sha256=evidence_sha256,
                )
            except Exception:
                current = runtime.task(task_id)
                if retry and current is not None and current.effect_uncertain:
                    self.ingress.mark_leased(tenant, task_id)
                raise
            self._sync_verified_outcome(tenant, result.task)
            return result

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
            if self.verified_mode:
                raise AdmissionError("use verified tenant dispatch")
            active_tenant = self._tenant_by_task.get(task_id)
            if active_tenant is not None:
                if active_tenant != tenant:
                    raise AdmissionError(f"task already belongs to tenant: {active_tenant}")
                resident = self.broker.runtime.task(task_id)
                if resident is None:
                    raise AdmissionError(
                        f"active tenant task missing from runtime: {task_id}; repair required"
                    )
                if is_terminal(resident):
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
                if resident is not None and not is_terminal(resident):
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
            if self.verified_mode:
                raise AdmissionError("use verified tenant completion")
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
            if self.verified_mode:
                raise AdmissionError("use verified tenant completion")
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
            elif is_terminal(result.task):
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
