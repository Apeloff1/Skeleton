"""metrics — lightweight infra meters for Pack A ultra-infra.

No external metrics backend required; snapshots are JSON-serializable
for API audit routes and tests.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MeterSnapshot:
    counters: Dict[str, float]
    gauges: Dict[str, float]
    histograms: Dict[str, Dict[str, float]]
    when: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {k: dict(v) for k, v in self.histograms.items()},
            "when": self.when,
        }


class CounterVec:
    def __init__(self, name: str) -> None:
        self.name = name
        self._values: Dict[Tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def labels(self, *label_values: str) -> "CounterChild":
        return CounterChild(self, tuple(label_values))

    def inc(self, labels: Tuple[str, ...], amount: float = 1.0) -> None:
        with self._lock:
            self._values[labels] = self._values.get(labels, 0.0) + float(amount)

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            return {"|".join(k) if k else "_": v for k, v in self._values.items()}


class CounterChild:
    def __init__(self, parent: CounterVec, labels: Tuple[str, ...]) -> None:
        self._parent = parent
        self._labels = labels

    def inc(self, amount: float = 1.0) -> None:
        self._parent.inc(self._labels, amount)


class GaugeVec:
    def __init__(self, name: str) -> None:
        self.name = name
        self._values: Dict[Tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def labels(self, *label_values: str) -> "GaugeChild":
        return GaugeChild(self, tuple(label_values))

    def set(self, labels: Tuple[str, ...], value: float) -> None:
        with self._lock:
            self._values[labels] = float(value)

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            return {"|".join(k) if k else "_": v for k, v in self._values.items()}


class GaugeChild:
    def __init__(self, parent: GaugeVec, labels: Tuple[str, ...]) -> None:
        self._parent = parent
        self._labels = labels

    def set(self, value: float) -> None:
        self._parent.set(self._labels, value)


class HistogramVec:
    def __init__(self, name: str, bounds: Optional[List[float]] = None) -> None:
        self.name = name
        self.bounds = bounds or [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
        self._sum: Dict[Tuple[str, ...], float] = {}
        self._count: Dict[Tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def labels(self, *label_values: str) -> "HistogramChild":
        return HistogramChild(self, tuple(label_values))

    def observe(self, labels: Tuple[str, ...], value: float) -> None:
        with self._lock:
            self._sum[labels] = self._sum.get(labels, 0.0) + float(value)
            self._count[labels] = self._count.get(labels, 0.0) + 1.0

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            out: Dict[str, Dict[str, float]] = {}
            keys = set(self._sum) | set(self._count)
            for k in keys:
                name = "|".join(k) if k else "_"
                out[name] = {
                    "sum": self._sum.get(k, 0.0),
                    "count": self._count.get(k, 0.0),
                }
            return out


class HistogramChild:
    def __init__(self, parent: HistogramVec, labels: Tuple[str, ...]) -> None:
        self._parent = parent
        self._labels = labels

    def observe(self, value: float) -> None:
        self._parent.observe(self._labels, value)


class InfraMeter:
    """Pack A meter registry."""

    def __init__(self) -> None:
        self.admit_total = CounterVec("pack_a_admit_total")
        self.admit_shed = CounterVec("pack_a_admit_shed")
        self.admit_emergency = CounterVec("pack_a_admit_emergency")
        self.staging_active = GaugeVec("pack_a_staging_active")
        self.admit_latency = HistogramVec("pack_a_admit_latency_seconds")
        self.cache_hits = CounterVec("pack_a_cache_hits")
        self.cache_misses = CounterVec("pack_a_cache_misses")
        self.coalesce_leaders = CounterVec("pack_a_coalesce_leaders")
        self.coalesce_joiners = CounterVec("pack_a_coalesce_joiners")
        self.buffer_leases = CounterVec("pack_a_buffer_leases")

    def snapshot(self) -> MeterSnapshot:
        return MeterSnapshot(
            counters={
                "admit_total": sum(self.admit_total.snapshot().values()),
                "admit_shed": sum(self.admit_shed.snapshot().values()),
                "admit_emergency": sum(self.admit_emergency.snapshot().values()),
                "cache_hits": sum(self.cache_hits.snapshot().values()),
                "cache_misses": sum(self.cache_misses.snapshot().values()),
                "coalesce_leaders": sum(self.coalesce_leaders.snapshot().values()),
                "coalesce_joiners": sum(self.coalesce_joiners.snapshot().values()),
                "buffer_leases": sum(self.buffer_leases.snapshot().values()),
            },
            gauges={
                "staging_active": sum(self.staging_active.snapshot().values()),
            },
            histograms=self.admit_latency.snapshot(),
            when=time.monotonic(),
        )


_METER = InfraMeter()


def default_meter() -> InfraMeter:
    return _METER


def reset_default_meter_for_tests() -> None:
    global _METER
    _METER = InfraMeter()


__all__ = [
    "CounterVec",
    "GaugeVec",
    "HistogramVec",
    "InfraMeter",
    "MeterSnapshot",
    "default_meter",
    "reset_default_meter_for_tests",
]
