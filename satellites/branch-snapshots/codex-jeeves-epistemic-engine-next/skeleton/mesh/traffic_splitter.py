"""Traffic splitter — weighted request routing across service versions.

Splits incoming traffic across backends by weight with sticky-session
support, shadow (mirror) traffic for safe version comparison, and
automatic weight adjustment driven by observed error rates. Pairs with
the canary controller for progressive rollouts.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Backend:
    name: str
    weight: int = 100
    healthy: bool = True
    requests: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0

    def error_rate(self) -> float:
        return self.errors / self.requests if self.requests else 0.0

    def mean_latency(self) -> float:
        return self.total_latency_ms / self.requests if self.requests else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "weight": self.weight,
            "healthy": self.healthy,
            "requests": self.requests,
            "error_rate": round(self.error_rate(), 4),
            "mean_latency_ms": round(self.mean_latency(), 2),
        }


class TrafficSplitter:
    """Weighted splitter with sticky sessions and shadowing."""

    def __init__(self, rng: Optional[random.Random] = None):
        self._backends: Dict[str, Backend] = {}
        self._sticky: Dict[str, str] = {}
        self._shadow: Optional[str] = None
        self._shadow_log: List[Dict[str, Any]] = []
        self._rng = rng or random.Random()

    def add_backend(self, name: str, weight: int = 100) -> Backend:
        b = Backend(name=name, weight=weight)
        self._backends[name] = b
        return b

    def set_weight(self, name: str, weight: int) -> None:
        self._backends[name].weight = max(0, weight)

    def mark_health(self, name: str, healthy: bool) -> None:
        self._backends[name].healthy = healthy

    def enable_shadow(self, backend: str) -> None:
        self._shadow = backend

    def disable_shadow(self) -> None:
        self._shadow = None

    def route(self, session_id: Optional[str] = None) -> Optional[str]:
        if session_id and session_id in self._sticky:
            name = self._sticky[session_id]
            if name in self._backends and self._backends[name].healthy:
                return name
        pool = [b for b in self._backends.values() if b.healthy and b.weight > 0]
        if not pool:
            return None
        total = sum(b.weight for b in pool)
        roll = self._rng.uniform(0, total)
        acc = 0.0
        for b in pool:
            acc += b.weight
            if roll <= acc:
                if session_id:
                    self._sticky[session_id] = b.name
                return b.name
        return pool[-1].name

    def record(self, backend: str, latency_ms: float, error: bool = False) -> None:
        b = self._backends.get(backend)
        if not b:
            return
        b.requests += 1
        b.total_latency_ms += latency_ms
        if error:
            b.errors += 1
        if self._shadow and backend != self._shadow:
            self._shadow_log.append({
                "primary": backend, "shadow": self._shadow,
                "latency_ms": latency_ms, "timestamp_ns": time.time_ns(),
            })

    def auto_rebalance(self, max_error_rate: float = 0.1) -> List[Dict[str, Any]]:
        """Shift weight away from backends breaching the error threshold."""
        actions: List[Dict[str, Any]] = []
        for b in self._backends.values():
            if b.requests >= 20 and b.error_rate() > max_error_rate and b.weight > 0:
                old = b.weight
                b.weight = max(1, b.weight // 2)
                actions.append({"backend": b.name, "old_weight": old, "new_weight": b.weight, "reason": "high_error_rate"})
        return actions

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "traffic-splitter-card",
            "backends": {n: b.to_dict() for n, b in self._backends.items()},
            "sticky_sessions": len(self._sticky),
            "shadow": self._shadow,
            "shadow_events": len(self._shadow_log),
        }
