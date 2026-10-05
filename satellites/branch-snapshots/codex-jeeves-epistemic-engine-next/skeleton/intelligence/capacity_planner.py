"""Capacity planner — resource growth modeling and headroom alerts.

Models capacity per resource (workers, cache entries, queue slots,
disk bytes) from observed usage series. Combines with the forecaster
to project saturation dates, recommends scale actions with lead time,
and tracks committed vs actual capacity for budget alignment.
"""
from __future__ import annotations

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

    def current_usage(self) -> float:
        return self.usage[-1] if self.usage else 0.0

    def headroom(self) -> float:
        return max(0.0, self.capacity - self.current_usage())

    def utilization(self) -> float:
        return self.current_usage() / self.capacity if self.capacity else 0.0


class CapacityPlanner:
    """Growth-aware capacity modeling with saturation prediction."""

    def __init__(self, forecaster: Any = None):
        self._pools: Dict[str, ResourcePool] = {}
        self._forecaster = forecaster
        self._recommendations: List[Dict[str, Any]] = []

    def define_pool(self, name: str, capacity: float, unit: str,
                    warn_fraction: float = 0.8) -> ResourcePool:
        pool = ResourcePool(name=name, capacity=capacity, unit=unit, warn_fraction=warn_fraction)
        self._pools[name] = pool
        return pool

    def record_usage(self, pool: str, usage: float) -> None:
        p = self._pools[pool]
        p.usage.append(usage)
        if len(p.usage) > 200:
            p.usage.pop(0)
        if self._forecaster:
            self._forecaster.feed(f"capacity.{pool}", usage)

    def resize(self, pool: str, new_capacity: float) -> None:
        self._pools[pool].capacity = new_capacity

    def saturation_estimate(self, pool: str) -> Dict[str, Any]:
        p = self._pools.get(pool)
        if not p:
            return {"pool": pool, "error": "unknown pool"}
        if len(p.usage) >= 2:
            growth = p.usage[-1] - p.usage[-2]
        else:
            growth = 0.0
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
            if p.utilization() >= p.warn_fraction:
                est = self.saturation_estimate(name)
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
            elif p.utilization() < 0.2 and len(p.usage) > 10:
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
                "utilization": round(p.utilization(), 3),
                "headroom": round(p.headroom(), 2),
            } for n, p in self._pools.items()},
            "recommendations": self.analyze(),
        }
