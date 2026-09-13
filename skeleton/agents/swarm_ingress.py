"""Transactional multi-tenant ingress governance for swarm workloads."""

from __future__ import annotations

from dataclasses import dataclass
import json
from threading import RLock

from skeleton.agents.swarm_fairness import FairShareLedger
from skeleton.agents.swarm_quota import Quota, QuotaExceeded, QuotaLedger
from skeleton.agents.swarm_rate_limit import TokenBucketLimiter


@dataclass(frozen=True, slots=True)
class IngressDecision:
    accepted: bool
    tenant: str
    reason: str
    payload_bytes: int
    rate_remaining: float


class SwarmIngressGovernor:
    """Coordinates rate, quota and fair-share state under one transaction boundary."""

    def __init__(
        self,
        *,
        rate_capacity: float = 100.0,
        rate_refill_per_second: float = 10.0,
        default_quota: Quota | None = None,
    ) -> None:
        self.rate = TokenBucketLimiter(capacity=rate_capacity, refill_per_second=rate_refill_per_second)
        self.quota = QuotaLedger(default_quota)
        self.fairness = FairShareLedger()
        self._lock = RLock()
        self._payload_by_task: dict[tuple[str, str], int] = {}
        self._phase_by_task: dict[tuple[str, str], str] = {}

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

    @staticmethod
    def payload_size(payload: object) -> int:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return len(encoded)

    def configure_tenant(self, tenant: str, *, quota: Quota | None = None, weight: int | None = None) -> None:
        tenant = self._tenant(tenant)
        if weight is not None:
            FairShareLedger.validate_weight(weight)
        with self._lock:
            if quota is not None:
                self.quota.configure(tenant, quota)
            if weight is not None:
                self.fairness.configure(tenant, weight=weight)

    def fork_empty(self) -> "SwarmIngressGovernor":
        """Clone admission policy without carrying live rate, quota, or task accounting."""
        with self._lock:
            limits = self.quota.configured_limits()
            weights = self.fairness.configured_weights()
            clone = SwarmIngressGovernor(
                rate_capacity=self.rate.capacity,
                rate_refill_per_second=self.rate.refill_per_second,
                default_quota=self.quota.default,
            )
            clone.fairness.default_weight = self.fairness.default_weight
            for tenant in sorted(set(limits) | set(weights)):
                clone.configure_tenant(
                    tenant,
                    quota=limits.get(tenant),
                    weight=weights.get(tenant),
                )
            return clone

    def admit(self, tenant: str, task_id: str, payload: object, *, cost: float = 1.0) -> IngressDecision:
        tenant = self._tenant(tenant)
        task_id = self._task_id(task_id)
        key = (tenant, task_id)
        payload_bytes = self.payload_size(payload)
        with self._lock:
            if key in self._phase_by_task:
                return IngressDecision(False, tenant, "task already accounted", payload_bytes, self.rate.remaining(tenant))
            usage = self.quota.snapshot().get(tenant, {"queued": 0, "leased": 0, "payload_bytes": 0})
            limit = self.quota.limit(tenant)
            if usage["queued"] + 1 > limit.max_queued:
                return IngressDecision(False, tenant, "queued quota exceeded", payload_bytes, self.rate.remaining(tenant))
            if usage["payload_bytes"] + payload_bytes > limit.max_payload_bytes:
                return IngressDecision(False, tenant, "payload quota exceeded", payload_bytes, self.rate.remaining(tenant))
            if not self.rate.allow(tenant, cost=cost):
                return IngressDecision(False, tenant, "rate limit exceeded", payload_bytes, self.rate.remaining(tenant))
            try:
                self.quota.reserve(tenant, queued=1, payload_bytes=payload_bytes)
            except QuotaExceeded as exc:
                self.rate.refund(tenant, cost=cost)
                return IngressDecision(False, tenant, str(exc), payload_bytes, self.rate.remaining(tenant))
            try:
                self.fairness.admit(tenant)
            except Exception:
                self.quota.release(tenant, queued=1, payload_bytes=payload_bytes)
                self.rate.refund(tenant, cost=cost)
                raise
            self._payload_by_task[key] = payload_bytes
            self._phase_by_task[key] = "queued"
            return IngressDecision(True, tenant, "admitted", payload_bytes, self.rate.remaining(tenant))

    def restore_task(self, tenant: str, task_id: str, payload: object, *, phase: str) -> None:
        """Rebuild quota/fair-share accounting without consuming ingress rate capacity."""
        tenant = self._tenant(tenant)
        task_id = self._task_id(task_id)
        if phase not in {"queued", "leased"}:
            raise ValueError(f"invalid ingress phase: {phase}")
        key = (tenant, task_id)
        payload_bytes = self.payload_size(payload)
        with self._lock:
            existing = self._phase_by_task.get(key)
            if existing is not None:
                if existing != phase:
                    raise ValueError(f"task already accounted in phase {existing}: {task_id}")
                return
            if phase == "queued":
                self.quota.reserve(tenant, queued=1, payload_bytes=payload_bytes)
            else:
                self.quota.reserve(tenant, leased=1, payload_bytes=payload_bytes)
            try:
                self.fairness.admit(tenant)
            except Exception:
                if phase == "queued":
                    self.quota.release(tenant, queued=1, payload_bytes=payload_bytes)
                else:
                    self.quota.release(tenant, leased=1, payload_bytes=payload_bytes)
                raise
            self._payload_by_task[key] = payload_bytes
            self._phase_by_task[key] = phase

    def phase(self, tenant: str, task_id: str) -> str | None:
        tenant = self._tenant(tenant)
        task_id = self._task_id(task_id)
        with self._lock:
            return self._phase_by_task.get((tenant, task_id))

    def mark_leased(self, tenant: str, task_id: str) -> None:
        tenant = self._tenant(tenant)
        task_id = self._task_id(task_id)
        key = (tenant, task_id)
        with self._lock:
            phase = self._phase_by_task.get(key)
            if phase != "queued":
                raise ValueError(f"task is not queued: {task_id}")
            self.quota.reserve(tenant, queued=-1, leased=1)
            self._phase_by_task[key] = "leased"

    def mark_requeued(self, tenant: str, task_id: str) -> None:
        tenant = self._tenant(tenant)
        task_id = self._task_id(task_id)
        key = (tenant, task_id)
        with self._lock:
            phase = self._phase_by_task.get(key)
            if phase != "leased":
                raise ValueError(f"task is not leased: {task_id}")
            self.quota.reserve(tenant, queued=1, leased=-1)
            self._phase_by_task[key] = "queued"

    def complete(self, tenant: str, task_id: str) -> None:
        tenant = self._tenant(tenant)
        task_id = self._task_id(task_id)
        key = (tenant, task_id)
        with self._lock:
            phase = self._phase_by_task.get(key)
            if phase is None:
                raise ValueError(f"task is not accounted: {task_id}")
            payload_bytes = self._payload_by_task[key]
            if phase not in {"queued", "leased"}:
                raise ValueError(f"invalid ingress phase: {phase}")

            self.fairness.complete(tenant)
            try:
                if phase == "queued":
                    self.quota.release(tenant, queued=1, payload_bytes=payload_bytes)
                else:
                    self.quota.release(tenant, leased=1, payload_bytes=payload_bytes)
            except Exception:
                self.fairness.rollback_complete(tenant)
                raise

            del self._phase_by_task[key]
            del self._payload_by_task[key]

    def preferred_tenant(self, tenants: list[str]) -> str | None:
        return self.fairness.preferred(tenants)

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "quota": self.quota.snapshot(),
                "fairness": self.fairness.snapshot(),
                "rate": self.rate.snapshot(),
                "accounted_tasks": len(self._phase_by_task),
                "phases": {
                    f"{tenant}:{task_id}": phase
                    for (tenant, task_id), phase in sorted(self._phase_by_task.items())
                },
            }
