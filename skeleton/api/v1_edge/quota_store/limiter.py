"""Distributed quotas for the /api/v1 edge.

:class:`DistributedQuotas` extends — it does not replace — the edge's own
:class:`~skeleton.api.v1_edge.quotas.TenantQuotas`. When a ``legacy``
``TenantQuotas`` is supplied it runs first (keeping its rolling-window
``x-quota-remaining`` quotas and its 429 codes), then the shared-store token
buckets from the :class:`~.policy.QuotaPlan` run, and the headers merge.

It keeps the ``check(tenant, quota_class)`` signature that ``build_v1_edge``
already calls, and adds ``check_request(tenant, spec, method)`` which the
edge prefers when present so route-scoped buckets see the route template.

Failure policy is **fail closed**: if the counter store raises
:class:`~.store.StoreUnavailable` the request is refused with ``503
EDGE.QUOTA.STORE_UNAVAILABLE`` in the standard error envelope plus a short
``Retry-After``, and an audit event is emitted. There is no "allow on error"
switch by design.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Tuple

from ..envelope import EdgeError
from ..quotas import TenantQuotas
from .headers import denial_headers, merge_legacy, quota_headers
from .memory import InMemoryCounterStore
from .policy import Bucket, QuotaPlan, tenant_digest
from .store import CounterStore, StoreUnavailable, TakeResult
from .telemetry import (AUDIT_DENIED, AUDIT_EXEMPT, AUDIT_RESET, AUDIT_STORE_DOWN,
                        QuotaTelemetry)

CODE_RATE_LIMITED = "EDGE.RATE.LIMITED"
CODE_STORE_DOWN = "EDGE.QUOTA.STORE_UNAVAILABLE"
CODE_TOO_COSTLY = "EDGE.QUOTA.COST_EXCEEDS_BURST"
STORE_DOWN_RETRY_AFTER_S = 1


class DistributedQuotas:
    def __init__(self, plan: QuotaPlan, *, store: Optional[CounterStore] = None,
                 legacy: Optional[TenantQuotas] = None,
                 telemetry: Optional[QuotaTelemetry] = None,
                 timer: Callable[[], float] = time.perf_counter):
        self.plan = plan
        self.store: CounterStore = store if store is not None else InMemoryCounterStore()
        self.legacy = legacy
        self.telemetry = telemetry or QuotaTelemetry()
        self._timer = timer

    # -- edge entry points --------------------------------------------------------
    def check(self, tenant: str, qclass: str) -> Dict[str, str]:
        """Back-compat entry (no route known): tenant-class bucket only."""
        return self._run(tenant, qclass, None, None)

    def check_request(self, tenant: Optional[str], spec, method: str) -> Dict[str, str]:
        return self._run(tenant, spec.quota_class, method, spec.path)

    # -- core ---------------------------------------------------------------------
    def _run(self, tenant: Optional[str], qclass: str, method: Optional[str],
             path_template: Optional[str]) -> Dict[str, str]:
        legacy_hdrs: Dict[str, str] = {}
        if self.legacy is not None:
            legacy_hdrs = self.legacy.check(tenant or "anonymous", qclass)
        if tenant is not None and tenant in self.plan.exempt_tenants:
            self.telemetry.audit(AUDIT_EXEMPT, tenant_ref=tenant_digest(tenant), quota_class=qclass)
            return legacy_hdrs
        if method is None or path_template is None:
            buckets = [b for b in self.plan.buckets(tenant, qclass, "ANY", "/") if b.scope == "tenant"]
            cost = 1.0
        else:
            buckets = self.plan.buckets(tenant, qclass, method, path_template)
            cost = self.plan.cost_for(method)
        charged: List[Tuple[Bucket, TakeResult]] = []
        store_name = getattr(self.store, "name", "unknown")
        for b in buckets:
            if cost > b.limit.burst:
                self.telemetry.decision(b.scope, b.label, "too_costly", 0, b.limit.burst, store_name)
                raise EdgeError(429, CODE_TOO_COSTLY, "request cost exceeds quota burst",
                                {"scope": b.scope, "cost": cost, "burst": b.limit.burst})
            t0 = self._timer()
            try:
                res = self.store.take(b.key, b.limit.spec, cost)
            except StoreUnavailable as exc:
                self.telemetry.store_error(store_name, "take")
                self.telemetry.audit(AUDIT_STORE_DOWN, tenant_ref=tenant_digest(tenant),
                                     scope=b.scope, name=b.label, backend=exc.backend)
                raise EdgeError(503, CODE_STORE_DOWN, "quota service unavailable",
                                {"scope": b.scope},
                                {"retry-after": str(STORE_DOWN_RETRY_AFTER_S)}) from None
            finally:
                self.telemetry.store_latency(store_name, (self._timer() - t0) * 1000.0)
            outcome = "allowed" if res.allowed else "denied"
            self.telemetry.decision(b.scope, b.label, outcome, res.remaining, res.capacity, store_name)
            charged.append((b, res))
            if not res.allowed:
                hdrs = denial_headers(charged, (b, res))
                self.telemetry.audit(AUDIT_DENIED, tenant_ref=tenant_digest(tenant), scope=b.scope,
                                     name=b.label, retry_after=hdrs["retry-after"])
                raise EdgeError(429, CODE_RATE_LIMITED, "rate limited",
                                {"quota_class": qclass, "scope": b.scope}, hdrs)
        return merge_legacy(legacy_hdrs, quota_headers(charged))

    # -- operator / introspection -------------------------------------------------
    def remaining(self, tenant: Optional[str], qclass: str, method: str,
                  path_template: str) -> Dict[str, int]:
        """Remaining tokens per scope without spending (for a usage endpoint)."""
        out: Dict[str, int] = {}
        for b in self.plan.buckets(tenant, qclass, method, path_template):
            try:
                out[b.scope] = self.store.peek(b.key, b.limit.spec).remaining_int
            except StoreUnavailable:
                self.telemetry.store_error(getattr(self.store, "name", "unknown"), "peek")
                raise EdgeError(503, CODE_STORE_DOWN, "quota service unavailable",
                                headers={"retry-after": str(STORE_DOWN_RETRY_AFTER_S)}) from None
        return out

    def reset(self, tenant: Optional[str], qclass: str, method: str, path_template: str,
              *, actor: str) -> List[str]:
        """Refill a tenant's buckets for one route (audited operator action)."""
        scopes = []
        for b in self.plan.buckets(tenant, qclass, method, path_template):
            if b.scope == "route":
                continue  # shared across tenants; never reset on one tenant's behalf
            self.store.reset(b.key)
            scopes.append(b.scope)
        self.telemetry.audit(AUDIT_RESET, tenant_ref=tenant_digest(tenant), actor=actor,
                             scopes=scopes, name=f"{method.upper()} {path_template}")
        return scopes

    def health_check(self) -> bool:
        """Plug into HealthRegistry.add('quota_store', quotas.health_check)."""
        try:
            return bool(self.store.healthy())
        except Exception:  # noqa: BLE001
            return False
