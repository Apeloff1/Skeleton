"""Resilience bulkheads — failure containment per caller/partition.

One bad tenant shouldn't poison the fortress. Bulkheads allocate a
bounded concurrency budget per partition; a partition that exhausts
it rejects cleanly instead of consuming global capacity.

- :class:`Bulkhead` — per-partition semaphore with queue-cap checks
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from skeleton.kernel.errors import KernelError


class BulkheadError(KernelError):
    code = "RES.BULKHEAD"


class Rejected(KernelError):
    code = "RES.BULKHEAD_FULL"
    http_status = 503


@dataclass
class BulkheadStats:
    in_flight: int = 0
    rejected: int = 0
    peak: int = 0


class Bulkhead:
    """Concurrency limiter; partitions get their own "pool" of permits."""

    def __init__(self, max_concurrent: int = 64) -> None:
        if max_concurrent <= 0:
            raise BulkheadError("max_concurrent must be positive")
        self._limit = max_concurrent
        self._partitions: Dict[str, BulkheadStats] = {}
        self._lock = threading.Lock()

    def acquire(self, partition: str) -> None:
        with self._lock:
            stats = self._partitions.setdefault(partition, BulkheadStats())
            if stats.in_flight >= self._limit:
                stats.rejected += 1
                raise Rejected("bulkhead full", context={"partition": partition})
            stats.in_flight += 1
            stats.peak = max(stats.peak, stats.in_flight)

    def release(self, partition: str) -> None:
        with self._lock:
            stats = self._partitions.get(partition)
            if stats is None or stats.in_flight <= 0:
                raise BulkheadError("release without acquire", context={"partition": partition})
            stats.in_flight -= 1

    def status(self, partition: str) -> BulkheadStats:
        return self._partitions.get(partition, BulkheadStats())
