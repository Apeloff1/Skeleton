"""Capacity planner — resource growth modeling and headroom alerts.

Models capacity per resource (workers, cache entries, queue slots,
disk bytes) from observed usage series. Combines with the forecaster
to project saturation dates, recommends scale actions with lead time,
and tracks committed vs actual capacity for budget alignment.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ResourcePool:
    name: str
    capacity: float
    unit: str
    usage: List[float] = field(default_factory=list)
    warn_fraction: float = 0.8

    def current_usage(self) -> float | None:
        if not self.usage:
            return None
        return float(self.usage[-1])

    def headroom(self) -> float | None:
        usage = self.current_usage()
        if usage is None:
            return None
        return self.capacity - usage

    def utilization(self) -> float | None:
        usage = self.current_usage()
        if usage is None:
            return None
        if self.capacity <= 0:
            return 1.0 if usage > 0 else 0.0
        return usage / self.capacity



def _positive_capacity(capacity: float) -> float:
    if isinstance(capacity, bool) or not isinstance(capacity, (int, float)) or float(capacity) <= 0:
        raise ValueError("capacity must be positive")
    return float(capacity)


def _warn_fraction(fraction: float) -> float:
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not 0.0 < float(fraction) <= 1.0:
        raise ValueError("warn_fraction must be in (0, 1]")
    return float(fraction)


class CapacityPlanner:
    """Growth-aware capacity modeling with saturation prediction."""

    def __init__(self, forecaster: Any = None):
        self._pools: Dict[str, ResourcePool] = {}
        self._forecaster = forecaster
        self._recommendations: List[Dict[str, Any]] = []

    def define_pool(self, name: str, capacity: float, unit: str,
                    warn_fraction: float = 0.8) -> ResourcePool:
        pool = ResourcePool(name=name, capacity=_positive_capacity(capacity), unit=unit,
                            warn_fraction=_warn_fraction(warn_fraction))
        self._pools[name] = pool
        return pool

    def record_usage(self, pool: str, usage: float) -> None:
        if pool not in self._pools:
            raise KeyError(pool)
        if isinstance(usage, bool) or not isinstance(usage, (int, float)) or not math.isfinite(float(usage)) or float(usage) < 0:
            raise ValueError("usage must be a finite non-negative number")
        p = self._pools[pool]
        p.usage.append(float(usage))
        if len(p.usage) > 200:
            p.usage.pop(0)
        if self._forecaster:
            self._forecaster.feed(f"capacity.{pool}", usage)

    def resize(self, pool: str, new_capacity: float) -> None:
        self._pools[pool].capacity = _positive_capacity(new_capacity)

    def record_shared_pressure(self, snapshot: Any) -> Dict[str, float]:
        """Feed durable shared queue/concurrency pressure into capacity history."""

        required = (
            "scope",
            "active",
            "queued",
            "max_concurrency",
            "max_queue_depth",
        )
        if any(not hasattr(snapshot, name) for name in required):
            raise TypeError("snapshot must expose the shared-pressure contract")
        scope = str(snapshot.scope).strip()
        if not scope:
            raise ValueError("shared pressure scope must not be empty")
        dimensions = {
            f"shared.{scope}.concurrency": (
                float(snapshot.active),
                float(snapshot.max_concurrency),
            ),
            f"shared.{scope}.queue": (
                float(snapshot.queued),
                float(snapshot.max_queue_depth),
            ),
        }
        result: Dict[str, float] = {}
        for name, (usage, capacity_value) in dimensions.items():
            if name not in self._pools:
                self.define_pool(name, capacity_value, "slots")
            elif self._pools[name].capacity != capacity_value:
                self.resize(name, capacity_value)
            self.record_usage(name, usage)
            result[name] = round(self._pools[name].utilization(), 6)
        return result

    def saturation_estimate(self, pool: str) -> Dict[str, Any]:
        if pool not in self._pools:
            raise KeyError(pool)
        p = self._pools[pool]
        if len(p.usage) < 2:
            raise ValueError("saturation needs two usage samples")
        growth = p.usage[-1] - p.usage[-2]
        if growth <= 0:
            return {"pool": pool, "saturates": False, "growth_per_step": round(growth, 4)}
        steps = p.headroom() / growth
        return {
            "pool": pool,
            "saturates": True,
            "steps_until_full": round(steps, 1),
            "growth_per_step": round(growth, 4),
            "current_utilization": round(p.utilization(), 3),
        }

    def analyze(self) -> List[Dict[str, Any]]:
        self._recommendations.clear()
        for name, p in self._pools.items():
            used = p.utilization()
            if used is None:
                continue
            if used >= p.warn_fraction:
                if len(p.usage) >= 2:
                    est = self.saturation_estimate(name)
                else:
                    est = {"pool": name, "saturates": None, "reason": "need two usage samples"}
                suggested = round(p.capacity * 1.5, 1)
                rec = {
                    "pool": name,
                    "action": "scale_up",
                    "current_capacity": p.capacity,
                    "suggested_capacity": suggested,
                    "utilization": round(p.utilization(), 3),
                    "saturation": est,
                    "urgency": "high" if p.utilization() >= 0.95 else "medium",
                }
                self._recommendations.append(rec)
            elif used < 0.2 and len(p.usage) > 10:
                self._recommendations.append({
                    "pool": name,
                    "action": "scale_down",
                    "current_capacity": p.capacity,
                    "suggested_capacity": round(p.capacity * 0.7, 1),
                    "utilization": round(p.utilization(), 3),
                    "urgency": "low",
                })
        return list(self._recommendations)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "capacity-planner-card",
            "pools": {n: {
                "capacity": p.capacity,
                "usage": p.current_usage(),
                "unit": p.unit,
                "utilization": None if p.utilization() is None else round(p.utilization(), 3),
                "headroom": None if p.headroom() is None else round(p.headroom(), 2),
            } for n, p in self._pools.items()},
            "recommendations": self.analyze(),
        }
