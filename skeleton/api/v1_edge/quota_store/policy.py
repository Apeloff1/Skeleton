"""Quota plan: which token buckets a request must pass, and their shapes.

Three bucket scopes, checked narrowest first so a denial at a narrow scope
never spends from a broader one:

1. ``route``        — one bucket per route template shared by *all* tenants
                      (protects an expensive endpoint as a whole). Optional.
2. ``tenant_route`` — one bucket per (tenant, route template). Optional.
3. ``tenant``       — one bucket per (tenant, quota class); the class comes
                      from :class:`~skeleton.api.v1_edge.registry.RouteSpec`.

Route templates (``"POST /projects"``), never concrete paths, are used in
keys, so ``/projects/1`` and ``/projects/2`` share a bucket and key
cardinality stays bounded by the route table.

Tenant ids are hashed into keys (sha256, truncated) so the store never holds
raw tenant identifiers and a crafted tenant id cannot inject key separators.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

from .store import BucketSpec

SCOPES = ("route", "tenant_route", "tenant")


@dataclass(frozen=True)
class Limit:
    """A token bucket: ``burst`` capacity refilled at ``rate_per_s``."""

    rate_per_s: float
    burst: int

    def __post_init__(self) -> None:
        if not (self.rate_per_s > 0 and math.isfinite(self.rate_per_s)):
            raise ValueError("rate_per_s must be positive and finite")
        if self.burst < 1:
            raise ValueError("burst must be >= 1")

    @classmethod
    def per_minute(cls, n: int, burst: Optional[int] = None) -> "Limit":
        return cls(n / 60.0, burst if burst is not None else n)

    @classmethod
    def per_hour(cls, n: int, burst: Optional[int] = None) -> "Limit":
        return cls(n / 3600.0, burst if burst is not None else n)

    @property
    def spec(self) -> BucketSpec:
        return BucketSpec(float(self.burst), self.rate_per_s)

    @property
    def window_s(self) -> int:
        """Seconds to refill a full burst; advertised as the policy window."""
        return max(1, int(math.ceil(self.burst / self.rate_per_s)))


@dataclass(frozen=True)
class Bucket:
    scope: str
    key: str
    limit: Limit
    label: str  # bounded-cardinality name for telemetry (class or route template)


def route_key(method: str, path_template: str) -> str:
    return f"{method.upper()} {path_template}"


def tenant_digest(tenant: Optional[str]) -> str:
    raw = (tenant or "anonymous").encode("utf-8", "surrogatepass")
    return hashlib.sha256(raw).hexdigest()[:24]


@dataclass
class QuotaPlan:
    """Configuration for :class:`~.limiter.DistributedQuotas`.

    ``tenant_limits`` must contain ``"default"``. Overrides are per tenant
    (raw id, as authenticated) and win over the class default — e.g. a paid
    plan. ``method_cost`` lets writes cost more than reads.
    """

    tenant_limits: Dict[str, Limit]
    tenant_overrides: Dict[Tuple[str, str], Limit] = field(default_factory=dict)
    route_limits: Dict[str, Limit] = field(default_factory=dict)
    tenant_route_limits: Dict[str, Limit] = field(default_factory=dict)
    tenant_route_overrides: Dict[Tuple[str, str], Limit] = field(default_factory=dict)
    method_cost: Mapping[str, float] = field(default_factory=dict)
    exempt_tenants: frozenset = frozenset()
    namespace: str = "v1"

    def __post_init__(self) -> None:
        if "default" not in self.tenant_limits:
            raise ValueError("tenant_limits needs a 'default' class")
        for k in list(self.route_limits) + list(self.tenant_route_limits):
            parts = k.split(" ", 1)
            if len(parts) != 2 or not parts[1].startswith("/"):
                raise ValueError(f"route limit key must look like 'GET /path', got {k!r}")
        for method, cost in self.method_cost.items():
            if not (cost > 0 and math.isfinite(cost)):
                raise ValueError(f"cost for {method} must be positive and finite")

    def cost_for(self, method: str) -> float:
        return float(self.method_cost.get(method.upper(), 1.0))

    def tenant_limit(self, tenant: str, qclass: str) -> Limit:
        return (self.tenant_overrides.get((tenant, qclass))
                or self.tenant_limits.get(qclass)
                or self.tenant_limits["default"])

    def buckets(self, tenant: Optional[str], qclass: str, method: str,
                path_template: str) -> List[Bucket]:
        """Buckets for one request, narrowest scope first."""
        t = tenant or "anonymous"
        rk = route_key(method, path_template)
        td = tenant_digest(t)
        ns = self.namespace
        out: List[Bucket] = []
        rl = self.route_limits.get(rk)
        if rl is not None:
            out.append(Bucket("route", f"{ns}:r:{rk}", rl, rk))
        trl = self.tenant_route_overrides.get((t, rk)) or self.tenant_route_limits.get(rk)
        if trl is not None:
            out.append(Bucket("tenant_route", f"{ns}:tr:{td}:{rk}", trl, rk))
        out.append(Bucket("tenant", f"{ns}:t:{td}:{qclass}", self.tenant_limit(t, qclass), qclass))
        return out
