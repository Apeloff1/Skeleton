"""Bulkheads — failure isolation between kernel subsystems.

One misbehaving consumer of the event bus must not starve the rest.
Bulkheads partition shared capacity (concurrency permits, queue slots)
into named pools so a runaway subsystem exhausts *its own* budget and
no one else's. Pattern from release engineering: compartmentalise like
a ship's hull.

- :class:`PermitPool` — bounded semaphore with acquire timeout and
  fair FIFO handoff tracking (no threads; permits are logical).
- :class:`BulkheadRegistry` — named pools with a reserved "system" pool
  that can never be fully claimed by tenants.
- :class:`BulkheadReport` — per-pool utilisation for telemetry.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .errors import KernelError


class BulkheadError(KernelError):
    code = "KRN.BULKHEAD"


class PermitExhausted(BulkheadError):
    code = "KRN.BULKHEAD_EXHAUSTED"
    http_status = 503


@dataclass
class Permit:
    pool: str
    holder: str
    acquired_at: float
    permit_id: int


class PermitPool:
    """Logical permit pool: try_acquire/acquire with per-holder caps."""

    def __init__(self, name: str, size: int, *, per_holder_cap: Optional[int] = None,
                 clock: Optional[Callable[[], float]] = None) -> None:
        if size < 1:
            raise BulkheadError("pool size must be >= 1", context={"pool": name, "size": size})
        self.name = name
        self.size = size
        self.per_holder_cap = per_holder_cap or size
        self._now = clock or time.monotonic
        self._permits: Dict[int, Permit] = {}
        self._next_id = 1
        self._acquisitions = 0
        self._rejections = 0

    def _holder_count(self, holder: str) -> int:
        return sum(1 for p in self._permits.values() if p.holder == holder)

    def try_acquire(self, holder: str) -> Permit:
        if len(self._permits) >= self.size:
            self._rejections += 1
            raise PermitExhausted(
                "bulkhead pool exhausted",
                context={"pool": self.name, "size": self.size, "holder": holder},
            )
        if self._holder_count(holder) >= self.per_holder_cap:
            self._rejections += 1
            raise PermitExhausted(
                "per-holder cap reached in bulkhead pool",
                context={"pool": self.name, "holder": holder, "cap": self.per_holder_cap},
            )
        permit = Permit(self.name, holder, self._now(), self._next_id)
        self._next_id += 1
        self._permits[permit.permit_id] = permit
        self._acquisitions += 1
        return permit

    def release(self, permit: Permit) -> None:
        held = self._permits.get(permit.permit_id)
        if held is None or held.holder != permit.holder:
            raise BulkheadError(
                "permit not held by this holder (double-release or forgery)",
                context={"pool": self.name, "permit": permit.permit_id, "holder": permit.holder},
            )
        del self._permits[permit.permit_id]

    def held_by(self, holder: str) -> Tuple[Permit, ...]:
        return tuple(p for p in self._permits.values() if p.holder == holder)

    @property
    def available(self) -> int:
        return self.size - len(self._permits)

    @property
    def utilisation(self) -> float:
        return len(self._permits) / self.size


@dataclass
class BulkheadReport:
    pool: str
    size: int
    in_use: int
    utilisation: float
    acquisitions: int
    rejections: int


class BulkheadRegistry:
    """Named pools plus a protected reserve the system always keeps."""

    SYSTEM_POOL = "__system__"

    def __init__(self, total_capacity: int, *, system_reserve: int = 1,
                 clock: Optional[Callable[[], float]] = None) -> None:
        if system_reserve < 0 or system_reserve >= total_capacity:
            raise BulkheadError(
                "reserve must satisfy 0 <= reserve < total",
                context={"total": total_capacity, "reserve": system_reserve},
            )
        self.total = total_capacity
        self.reserve = system_reserve
        self._clock = clock or time.monotonic
        self._pools: Dict[str, PermitPool] = {
            self.SYSTEM_POOL: PermitPool(self.SYSTEM_POOL, system_reserve, clock=self._clock)
        } if system_reserve else {}
        self._tenant_budget = total_capacity - system_reserve

    def create_pool(self, name: str, size: int, *, per_holder_cap: Optional[int] = None) -> PermitPool:
        if name in self._pools:
            raise BulkheadError("pool already exists", context={"pool": name})
        allocated = sum(p.size for n, p in self._pools.items() if n != self.SYSTEM_POOL)
        if allocated + size > self._tenant_budget:
            raise BulkheadError(
                "pool would exceed tenant budget (system reserve protected)",
                context={"pool": name, "requested": size,
                         "allocated": allocated, "budget": self._tenant_budget},
            )
        pool = PermitPool(name, size, per_holder_cap=per_holder_cap, clock=self._clock)
        self._pools[name] = pool
        return pool

    def pool(self, name: str) -> PermitPool:
        p = self._pools.get(name)
        if p is None:
            raise BulkheadError("unknown pool", context={"pool": name})
        return p

    def report(self) -> Tuple[BulkheadReport, ...]:
        return tuple(
            BulkheadReport(
                pool=p.name,
                size=p.size,
                in_use=p.size - p.available,
                utilisation=round(p.utilisation, 4),
                acquisitions=p._acquisitions,
                rejections=p._rejections,
            )
            for p in sorted(self._pools.values(), key=lambda x: x.name)
        )

    def pools(self) -> Tuple[str, ...]:
        return tuple(sorted(self._pools))
