"""Distributed quotas for the /api/v1 edge: shared counter store + token buckets.

Extends :mod:`skeleton.api.v1_edge.quotas` (per-process TenantQuotas) with a
:class:`CounterStore` interface so edge replicas share per-tenant and
per-route token buckets, RateLimit-* client headers, fail-closed 503 on store
outage, and audit/metrics through Pack F :class:`GateTelemetry`.
"""
from __future__ import annotations

from .headers import quota_headers
from .limiter import (CODE_RATE_LIMITED, CODE_STORE_DOWN, CODE_TOO_COSTLY,
                      DistributedQuotas)
from .memory import InMemoryCounterStore
from .policy import Bucket, Limit, QuotaPlan, route_key, tenant_digest
from .remote import TAKE_SCRIPT, RemoteCounterStore
from .store import BucketSpec, CounterStore, StoreUnavailable, TakeResult, compute_take
from .telemetry import QuotaTelemetry

__all__ = [
    "Bucket", "BucketSpec", "CODE_RATE_LIMITED", "CODE_STORE_DOWN", "CODE_TOO_COSTLY",
    "CounterStore", "DistributedQuotas", "InMemoryCounterStore", "Limit", "QuotaPlan",
    "QuotaTelemetry", "RemoteCounterStore", "StoreUnavailable", "TAKE_SCRIPT", "TakeResult",
    "compute_take", "quota_headers", "route_key", "tenant_digest",
]
