"""Cost tracker — resource and compute cost accounting per subsystem.

Tracks cost events (compute seconds, storage bytes, egress bytes,
API calls) with unit pricing, rolls up per subsystem and per day,
and projects monthly spend. Fires dashboard alerts when the daily
burn exceeds the configured budget.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


DAY_NS = 86_400_000_000_000


DEFAULT_PRICING = {
    "compute_second": 0.0000167,
    "storage_gb_month": 0.023,
    "egress_gb": 0.09,
    "api_call": 0.0000004,
}


@dataclass
class CostEvent:
    timestamp_ns: int
    subsystem: str
    resource: str
    quantity: float
    cost_usd: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns,
            "subsystem": self.subsystem,
            "resource": self.resource,
            "quantity": self.quantity,
            "cost_usd": round(self.cost_usd, 6),
        }


class CostTracker:
    """Cost accounting with budgets and projections."""

    def __init__(self, pricing: Optional[Dict[str, float]] = None, daily_budget_usd: float = 10.0):
        self.pricing = {**DEFAULT_PRICING, **(pricing or {})}
        self.daily_budget_usd = daily_budget_usd
        self._events: List[CostEvent] = []

    def record(self, subsystem: str, resource: str, quantity: float,
               unit_cost: Optional[float] = None) -> CostEvent:
        unit = unit_cost if unit_cost is not None else self.pricing.get(resource, 0.0)
        event = CostEvent(time.time_ns(), subsystem, resource, quantity, quantity * unit)
        self._events.append(event)
        return event

    def _events_since(self, ns_ago: int) -> List[CostEvent]:
        cutoff = time.time_ns() - ns_ago
        return [e for e in self._events if e.timestamp_ns >= cutoff]

    def spend_today(self) -> float:
        return sum(e.cost_usd for e in self._events_since(DAY_NS))

    def by_subsystem(self, since_ns: Optional[int] = None) -> Dict[str, float]:
        events = self._events_since(since_ns) if since_ns else self._events
        out: Dict[str, float] = {}
        for e in events:
            out[e.subsystem] = out.get(e.subsystem, 0.0) + e.cost_usd
        return {k: round(v, 6) for k, v in sorted(out.items(), key=lambda kv: -kv[1])}

    def by_resource(self, since_ns: Optional[int] = None) -> Dict[str, float]:
        events = self._events_since(since_ns) if since_ns else self._events
        out: Dict[str, float] = {}
        for e in events:
            out[e.resource] = out.get(e.resource, 0.0) + e.cost_usd
        return {k: round(v, 6) for k, v in sorted(out.items(), key=lambda kv: -kv[1])}

    def monthly_projection(self) -> float:
        today = self.spend_today()
        return round(today * 30, 2)

    def budget_status(self) -> Dict[str, Any]:
        spent = self.spend_today()
        return {
            "spent_today_usd": round(spent, 4),
            "daily_budget_usd": self.daily_budget_usd,
            "remaining_usd": round(self.daily_budget_usd - spent, 4),
            "over_budget": spent > self.daily_budget_usd,
            "utilization": round(spent / self.daily_budget_usd, 3) if self.daily_budget_usd else 0.0,
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "cost-card",
            "budget": self.budget_status(),
            "by_subsystem_today": self.by_subsystem(DAY_NS),
            "by_resource_today": self.by_resource(DAY_NS),
            "monthly_projection_usd": self.monthly_projection(),
            "events": len(self._events),
        }
