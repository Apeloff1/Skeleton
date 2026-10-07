"""Leases with fencing tokens — safe mutual exclusion across the swarm.

A lease alone is not enough: an agent can hold a lease, get paused by
the scheduler or GC, wake up after expiry, and keep writing as if it
still owned the resource — split-brain by stop-the-world. The fix is
the classic fencing token: every lease carries a strictly monotonic
number, and any consumer of the resource rejects operations stamped
with an older token than it has already seen.

This module provides:

- :class:`Lease` — a grant with holder, resource, expiry, and fence.
- :class:`LeaseManager` — acquire/renew/release/steal with re-entrant
  renewal semantics and lazy expiry.
- :class:`FencingGate` — the consumer-side check: remembers the highest
  fence seen per resource and rejects stale writers.

Injectable clock, no threads, no I/O.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Callable, Dict, Optional, Tuple

from .errors import KernelError


class LeaseError(KernelError):
    code = "KRN.LEASE"
    http_status = 409


class LeaseHeldError(LeaseError):
    code = "KRN.LEASE_HELD"


class FenceError(LeaseError):
    code = "KRN.FENCE_STALE"
    http_status = 410


@dataclass(frozen=True)
class Lease:
    resource: str
    holder: str
    fence: int
    granted_at: float
    expires_at: float

    def is_expired(self, now: float) -> bool:
        return now >= self.expires_at

    @property
    def ttl_s(self) -> float:
        return self.expires_at - self.granted_at


class LeaseManager:
    """Issues and tracks leases; fences are monotonic per manager."""

    def __init__(
        self,
        *,
        ttl_s: float = 10.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if ttl_s <= 0:
            raise LeaseError("lease ttl must be positive", context={"ttl": ttl_s})
        self.ttl_s = ttl_s
        self._now = clock or time.monotonic
        self._leases: Dict[str, Lease] = {}
        self._fence = 0

    def _next_fence(self) -> int:
        self._fence += 1
        return self._fence

    def current(self, resource: str) -> Optional[Lease]:
        lease = self._leases.get(resource)
        if lease is not None and lease.is_expired(self._now()):
            del self._leases[resource]
            return None
        return lease

    def acquire(self, resource: str, holder: str, *, ttl_s: Optional[float] = None) -> Lease:
        live = self.current(resource)
        if live is not None:
            if live.holder == holder:
                return self.renew(resource, holder)
            raise LeaseHeldError(
                "resource already leased",
                context={"resource": resource, "holder": live.holder,
                         "fence": live.fence, "expires_in_s": round(live.expires_at - self._now(), 3)},
            )
        now = self._now()
        lease = Lease(resource, holder, self._next_fence(), now, now + (ttl_s or self.ttl_s))
        self._leases[resource] = lease
        return lease

    def renew(self, resource: str, holder: str, *, ttl_s: Optional[float] = None) -> Lease:
        live = self.current(resource)
        if live is None or live.holder != holder:
            raise LeaseError(
                "cannot renew a lease you do not hold",
                context={"resource": resource, "holder": holder},
            )
        now = self._now()
        renewed = replace(live, expires_at=now + (ttl_s or self.ttl_s))
        self._leases[resource] = renewed
        return renewed

    def release(self, resource: str, holder: str) -> bool:
        live = self.current(resource)
        if live is None or live.holder != holder:
            return False
        del self._leases[resource]
        return True

    def steal(self, resource: str, holder: str, *, ttl_s: Optional[float] = None) -> Lease:
        """Force-take the lease; the old holder's fence is now stale."""
        now = self._now()
        lease = Lease(resource, holder, self._next_fence(), now, now + (ttl_s or self.ttl_s))
        self._leases[resource] = lease
        return lease

    def held(self) -> Tuple[Lease, ...]:
        return tuple(l for r in list(self._leases) if (l := self.current(r)) is not None)


class FencingGate:
    """Consumer-side guard. Wraps the actual write path:

        gate.check(resource, lease.fence)   # raises FenceError if stale
        store.write(resource, payload)
    """

    def __init__(self) -> None:
        self._highest: Dict[str, int] = {}

    def check(self, resource: str, fence: int) -> None:
        highest = self._highest.get(resource, -1)
        if fence <= highest:
            raise FenceError(
                "stale fencing token — a newer lease has touched this resource",
                context={"resource": resource, "fence": fence, "highest_seen": highest},
            )
        self._highest[resource] = fence

    def reset(self, resource: Optional[str] = None) -> None:
        if resource is None:
            self._highest.clear()
        else:
            self._highest.pop(resource, None)
