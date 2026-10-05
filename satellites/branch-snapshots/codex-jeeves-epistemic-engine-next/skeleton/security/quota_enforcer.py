"""Quota enforcer — per-actor and per-subsystem resource quotas.

Enforces usage quotas (requests/day, compute seconds, storage bytes,
task submissions) with soft and hard limits, period-based resets, and
grace warnings. Quota breaches are logged to the audit log and can
fire dashboard alerts at configurable thresholds.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Quota:
    name: str
    resource: str
    limit: float
    period_s: float = 86400.0
    soft_fraction: float = 0.8
    used: float = 0.0
    period_start_ns: int = 0

    def reset_if_expired(self) -> None:
        if self.period_start_ns == 0:
            self.period_start_ns = time.time_ns()
            return
        if (time.time_ns() - self.period_start_ns) / 1e9 >= self.period_s:
            self.used = 0.0
            self.period_start_ns = time.time_ns()

    def utilization(self) -> float:
        return self.used / self.limit if self.limit else 0.0

    def soft_limit(self) -> float:
        return self.limit * self.soft_fraction


class QuotaEnforcer:
    """Multi-resource quota enforcement with soft/hard limits."""

    def __init__(self):
        self._quotas: Dict[str, Quota] = {}
        self._violations: List[Dict[str, Any]] = []
        self._warnings: List[Dict[str, Any]] = []

    def define(self, key: str, resource: str, limit: float,
               period_s: float = 86400.0, soft_fraction: float = 0.8) -> Quota:
        q = Quota(name=key, resource=resource, limit=limit, period_s=period_s, soft_fraction=soft_fraction)
        self._quotas[key] = q
        return q

    def consume(self, key: str, amount: float = 1.0, actor: str = "system") -> Dict[str, Any]:
        q = self._quotas.get(key)
        if not q:
            return {"allowed": True, "reason": "no quota defined"}
        q.reset_if_expired()
        projected = q.used + amount
        if projected > q.limit:
            self._violations.append({
                "quota": key, "actor": actor, "amount": amount,
                "used": q.used, "limit": q.limit, "timestamp_ns": time.time_ns(),
            })
            return {
                "allowed": False,
                "reason": "hard limit exceeded",
                "used": q.used,
                "limit": q.limit,
                "resets_in_s": q.period_s - (time.time_ns() - q.period_start_ns) / 1e9,
            }
        q.used = projected
        result: Dict[str, Any] = {"allowed": True, "used": q.used, "limit": q.limit, "utilization": round(q.utilization(), 3)}
        if projected > q.soft_limit():
            warning = {"quota": key, "actor": actor, "utilization": q.utilization(), "timestamp_ns": time.time_ns()}
            self._warnings.append(warning)
            result["warning"] = "soft limit reached"
        return result

    def remaining(self, key: str) -> Optional[float]:
        q = self._quotas.get(key)
        if not q:
            return None
        q.reset_if_expired()
        return max(0.0, q.limit - q.used)

    def reset(self, key: str) -> bool:
        q = self._quotas.get(key)
        if not q:
            return False
        q.used = 0.0
        q.period_start_ns = time.time_ns()
        return True

    def card(self) -> Dict[str, Any]:
        for q in self._quotas.values():
            q.reset_if_expired()
        return {
            "kind": "quota-card",
            "quotas": {k: {
                "resource": q.resource,
                "used": q.used,
                "limit": q.limit,
                "utilization": round(q.utilization(), 3),
                "over_soft": q.used > q.soft_limit(),
            } for k, q in self._quotas.items()},
            "violations": len(self._violations),
            "warnings": len(self._warnings),
            "recent_violations": self._violations[-5:],
        }
