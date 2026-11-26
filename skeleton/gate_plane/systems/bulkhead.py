"""Per-system concurrency bulkheads.

Each recovered system gets its own in-flight cap so a stalled system (a
slow local model, a long GameForge build) cannot exhaust the worker pool
for the others. Acquisition never blocks: a full bulkhead rejects at once
and the edge answers 503 with ``Retry-After``. Permits are tracked per
token so a double release is detected instead of silently inflating
capacity.
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass
from typing import Dict, Mapping, Optional


class BulkheadError(RuntimeError):
    pass


@dataclass(frozen=True)
class Permit:
    system: str
    token: int


class Bulkhead:
    def __init__(self, system: str, limit: int) -> None:
        if int(limit) < 1:
            raise ValueError("bulkhead limit must be >= 1")
        self.system = system
        self.limit = int(limit)
        self._held: set[int] = set()
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self.rejected = 0
        self.admitted = 0
        self.peak = 0

    @property
    def in_flight(self) -> int:
        with self._lock:
            return len(self._held)

    def try_acquire(self) -> Optional[Permit]:
        with self._lock:
            if len(self._held) >= self.limit:
                self.rejected += 1
                return None
            tok = next(self._ids)
            self._held.add(tok)
            self.admitted += 1
            self.peak = max(self.peak, len(self._held))
            return Permit(self.system, tok)

    def release(self, permit: Permit) -> None:
        if permit.system != self.system:
            raise BulkheadError(f"permit for {permit.system!r} released on {self.system!r}")
        with self._lock:
            if permit.token not in self._held:
                raise BulkheadError(f"permit {permit.token} already released")
            self._held.discard(permit.token)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "limit": self.limit, "in_flight": len(self._held), "admitted": self.admitted,
                "rejected": self.rejected, "peak": self.peak,
            }


class BulkheadRegistry:
    def __init__(self, limits: Optional[Mapping[str, int]] = None) -> None:
        self._bulkheads: Dict[str, Bulkhead] = {}
        self._lock = threading.Lock()
        for name, lim in (limits or {}).items():
            self.configure(name, lim)

    def configure(self, system: str, limit: int) -> Bulkhead:
        with self._lock:
            if system in self._bulkheads:
                raise ValueError(f"bulkhead for {system!r} already configured")
            bh = Bulkhead(system, limit)
            self._bulkheads[system] = bh
            return bh

    def get(self, system: str) -> Bulkhead:
        with self._lock:
            bh = self._bulkheads.get(system)
        if bh is None:
            raise BulkheadError(f"no bulkhead configured for {system!r}")
        return bh

    def stats(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            items = list(self._bulkheads.items())
        return {k: v.stats() for k, v in sorted(items)}


__all__ = ["Bulkhead", "BulkheadError", "BulkheadRegistry", "Permit"]
