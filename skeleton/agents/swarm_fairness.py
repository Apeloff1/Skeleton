"""Thread-safe weighted fair-share accounting for multi-tenant swarm admission."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock


@dataclass(slots=True)
class TenantShare:
    weight: int = 1
    admitted: int = 0
    completed: int = 0
    inflight: int = 0

    @property
    def virtual_load(self) -> float:
        return self.inflight / max(1, self.weight)


@dataclass(slots=True)
class FairShareLedger:
    default_weight: int = 1
    _tenants: dict[str, TenantShare] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.default_weight < 1:
            raise ValueError("default_weight must be positive")

    @staticmethod
    def _tenant(tenant: str) -> str:
        tenant = tenant.strip()
        if not tenant:
            raise ValueError("tenant must not be empty")
        return tenant

    def configure(self, tenant: str, *, weight: int) -> TenantShare:
        tenant = self._tenant(tenant)
        if weight < 1:
            raise ValueError("weight must be positive")
        with self._lock:
            share = self._tenants.setdefault(tenant, TenantShare(weight=self.default_weight))
            share.weight = weight
            return share

    def admit(self, tenant: str) -> TenantShare:
        tenant = self._tenant(tenant)
        with self._lock:
            share = self._tenants.setdefault(tenant, TenantShare(weight=self.default_weight))
            share.admitted += 1
            share.inflight += 1
            return share

    def complete(self, tenant: str) -> TenantShare:
        tenant = self._tenant(tenant)
        with self._lock:
            share = self._tenants.setdefault(tenant, TenantShare(weight=self.default_weight))
            if share.inflight <= 0:
                raise ValueError(f"tenant has no inflight work: {tenant}")
            share.inflight -= 1
            share.completed += 1
            return share

    def preferred(self, tenants: list[str]) -> str | None:
        if not tenants:
            return None
        normalized = [self._tenant(tenant) for tenant in tenants]
        with self._lock:
            def score(tenant: str) -> tuple[float, str]:
                share = self._tenants.setdefault(tenant, TenantShare(weight=self.default_weight))
                return share.virtual_load, tenant
            return min(normalized, key=score)

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        with self._lock:
            return {
                tenant: {
                    "weight": share.weight,
                    "admitted": share.admitted,
                    "completed": share.completed,
                    "inflight": share.inflight,
                    "virtual_load": round(share.virtual_load, 6),
                }
                for tenant, share in sorted(self._tenants.items())
            }
