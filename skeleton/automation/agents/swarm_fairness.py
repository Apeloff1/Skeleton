"""Thread-safe weighted fair-share accounting for multi-tenant swarm admission."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock


@dataclass(frozen=True, slots=True)
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
        self.default_weight = self._weight(self.default_weight, "default_weight")

    @staticmethod
    def _weight(weight: int, name: str = "weight") -> int:
        if isinstance(weight, bool) or not isinstance(weight, int) or weight < 1:
            raise ValueError(f"{name} must be a positive integer")
        return weight

    @classmethod
    def validate_weight(cls, weight: int, name: str = "weight") -> int:
        """Validate and return a fair-share weight without mutating ledger state."""
        return cls._weight(weight, name)

    @staticmethod
    def _tenant(tenant: str) -> str:
        tenant = tenant.strip()
        if not tenant:
            raise ValueError("tenant must not be empty")
        return tenant

    def configure(self, tenant: str, *, weight: int) -> TenantShare:
        tenant = self._tenant(tenant)
        weight = self._weight(weight)
        with self._lock:
            current = self._tenants.get(tenant, TenantShare(weight=self.default_weight))
            share = TenantShare(weight=weight, admitted=current.admitted, completed=current.completed, inflight=current.inflight)
            self._tenants[tenant] = share
            return share

    def configured_weights(self) -> dict[str, int]:
        """Return configured tenant weights without exposing live accounting state."""
        with self._lock:
            return {tenant: share.weight for tenant, share in sorted(self._tenants.items())}

    def admit(self, tenant: str) -> TenantShare:
        tenant = self._tenant(tenant)
        with self._lock:
            current = self._tenants.get(tenant, TenantShare(weight=self.default_weight))
            share = TenantShare(
                weight=current.weight,
                admitted=current.admitted + 1,
                completed=current.completed,
                inflight=current.inflight + 1,
            )
            self._tenants[tenant] = share
            return share

    def complete(self, tenant: str) -> TenantShare:
        tenant = self._tenant(tenant)
        with self._lock:
            current = self._tenants.get(tenant, TenantShare(weight=self.default_weight))
            if current.inflight <= 0:
                raise ValueError(f"tenant has no inflight work: {tenant}")
            share = TenantShare(
                weight=current.weight,
                admitted=current.admitted,
                completed=current.completed + 1,
                inflight=current.inflight - 1,
            )
            self._tenants[tenant] = share
            return share

    def rollback_complete(self, tenant: str) -> TenantShare:
        """Undo one completion without changing the historical admission count."""
        tenant = self._tenant(tenant)
        with self._lock:
            current = self._tenants.get(tenant, TenantShare(weight=self.default_weight))
            if current.completed <= 0:
                raise ValueError(f"tenant has no completed work to roll back: {tenant}")
            share = TenantShare(
                weight=current.weight,
                admitted=current.admitted,
                completed=current.completed - 1,
                inflight=current.inflight + 1,
            )
            self._tenants[tenant] = share
            return share

    def preferred(self, tenants: list[str]) -> str | None:
        if not tenants:
            return None
        normalized = [self._tenant(tenant) for tenant in tenants]
        with self._lock:
            def score(tenant: str) -> tuple[float, str]:
                share = self._tenants.get(tenant, TenantShare(weight=self.default_weight))
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
