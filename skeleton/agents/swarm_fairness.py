"""Weighted fair-share accounting for multi-tenant swarm admission."""

from __future__ import annotations

from dataclasses import dataclass, field


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

    def configure(self, tenant: str, *, weight: int) -> TenantShare:
        tenant = tenant.strip()
        if not tenant:
            raise ValueError("tenant must not be empty")
        if weight < 1:
            raise ValueError("weight must be positive")
        share = self._tenants.setdefault(tenant, TenantShare())
        share.weight = weight
        return share

    def admit(self, tenant: str) -> TenantShare:
        share = self._tenants.setdefault(tenant, TenantShare(weight=self.default_weight))
        share.admitted += 1
        share.inflight += 1
        return share

    def complete(self, tenant: str) -> TenantShare:
        share = self._tenants.setdefault(tenant, TenantShare(weight=self.default_weight))
        if share.inflight > 0:
            share.inflight -= 1
        share.completed += 1
        return share

    def preferred(self, tenants: list[str]) -> str | None:
        if not tenants:
            return None
        return min(tenants, key=lambda tenant: (self._tenants.setdefault(tenant, TenantShare(weight=self.default_weight)).virtual_load, tenant))

    def snapshot(self) -> dict[str, dict[str, float | int]]:
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
