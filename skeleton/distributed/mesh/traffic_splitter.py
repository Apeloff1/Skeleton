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
    ewma_latency_ms: float = 0.0
    quality_score: float = 1.0
    in_flight: int = 0
    max_concurrency: int = 0
    base_weight: int = 0

    def __post_init__(self) -> None:
        if self.base_weight <= 0:
            self.base_weight = max(1, int(self.weight))

    def error_rate(self) -> float:
        return self.errors / self.requests if self.requests else 0.0

    def mean_latency(self) -> float:
        return self.total_latency_ms / self.requests if self.requests else 0.0

    def has_capacity(self) -> bool:
        if not self.healthy or self.weight <= 0:
            return False
        if self.max_concurrency > 0 and self.in_flight >= self.max_concurrency:
            return False
        return True

    def effective_weight(self, *, latency_budget_ms: float = 0.0) -> float:
        if not self.has_capacity():
            return 0.0
        reliability = max(0.05, 1.0 - min(0.95, self.error_rate()))
        quality = max(0.05, float(self.quality_score))
        lat_factor = 1.0
        obs_lat = self.ewma_latency_ms if self.ewma_latency_ms > 0.0 else self.mean_latency()
        if latency_budget_ms > 0.0 and obs_lat > latency_budget_ms:
            lat_factor = 1.0 / (1.0 + (obs_lat - latency_budget_ms) / latency_budget_ms)
        load_factor = 1.0
        if self.max_concurrency > 0:
            utilization = min(0.95, float(self.in_flight) / float(self.max_concurrency))
            load_factor = max(0.1, 1.0 - 0.5 * utilization)
        return max(0.01, float(self.weight) * reliability * quality * lat_factor * load_factor)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "weight": self.weight,
            "healthy": self.healthy,
            "requests": self.requests,
            "error_rate": round(self.error_rate(), 4),
            "mean_latency_ms": round(self.mean_latency(), 2),
            "ewma_latency_ms": round(self.ewma_latency_ms, 2),
            "quality_score": round(self.quality_score, 4),
            "in_flight": self.in_flight,
            "max_concurrency": self.max_concurrency,
        }


class TrafficSplitter:
    """Weighted splitter with sticky sessions, shadowing, and adaptive QoS routing."""

    def __init__(self, rng: Optional[random.Random] = None):
        self._backends: Dict[str, Backend] = {}
        self._sticky: Dict[str, str] = {}
        self._shadow: Optional[str] = None
        self._shadow_log: List[Dict[str, Any]] = []
        self._rng = rng or random.Random()

    def add_backend(
        self,
        name: str,
        weight: int = 100,
        *,
        max_concurrency: int = 0,
        quality_score: float = 1.0,
    ) -> Backend:
        b = Backend(
            name=name,
            weight=weight,
            max_concurrency=max(0, int(max_concurrency)),
            quality_score=max(0.05, float(quality_score)),
            base_weight=max(1, int(weight)),
        )
        self._backends[name] = b
        return b

    def set_weight(self, name: str, weight: int) -> None:
        self._backends[name].weight = max(0, weight)
        if weight > 0:
            self._backends[name].base_weight = max(1, int(weight))

    def set_quality(self, name: str, quality_score: float) -> None:
        if name in self._backends:
            self._backends[name].quality_score = max(0.05, float(quality_score))

    def mark_health(self, name: str, healthy: bool) -> None:
        self._backends[name].healthy = healthy

    def enable_shadow(self, backend: str) -> None:
        self._shadow = backend

    def disable_shadow(self) -> None:
        self._shadow = None

    def route(
        self,
        session_id: Optional[str] = None,
        *,
        latency_aware: bool = False,
        latency_budget_ms: float = 100.0,
    ) -> Optional[str]:
        if session_id and session_id in self._sticky:
            name = self._sticky[session_id]
            if name in self._backends and self._backends[name].has_capacity():
                return name
        pool = [b for b in self._backends.values() if b.has_capacity()]
        if not pool:
            return None
        if latency_aware:
            weights = [b.effective_weight(latency_budget_ms=latency_budget_ms) for b in pool]
        else:
            weights = [float(b.weight) for b in pool]
        total = sum(weights)
        if total <= 0.0:
            return None
        roll = self._rng.uniform(0.0, total)
        acc = 0.0
        for b, w in zip(pool, weights):
            acc += w
            if roll <= acc:
                if session_id:
                    self._sticky[session_id] = b.name
                return b.name
        chosen = pool[-1].name
        if session_id:
            self._sticky[session_id] = chosen
        return chosen

    def acquire_route(
        self,
        session_id: Optional[str] = None,
        *,
        latency_aware: bool = True,
        latency_budget_ms: float = 100.0,
    ) -> Optional[str]:
        chosen = self.route(
            session_id=session_id,
            latency_aware=latency_aware,
            latency_budget_ms=latency_budget_ms,
        )
        if chosen is not None and chosen in self._backends:
            self._backends[chosen].in_flight += 1
        return chosen

    def release_route(
        self,
        backend: str,
        latency_ms: float,
        error: bool = False,
    ) -> None:
        b = self._backends.get(backend)
        if b is not None and b.in_flight > 0:
            b.in_flight -= 1
        self.record(backend, latency_ms, error=error)

    def record(
        self,
        backend: str,
        latency_ms: float,
        error: bool = False,
        *,
        ewma_alpha: float = 0.2,
    ) -> None:
        b = self._backends.get(backend)
        if not b:
            return
        b.requests += 1
        lat = max(0.0, float(latency_ms))
        b.total_latency_ms += lat
        alpha = max(0.01, min(1.0, float(ewma_alpha)))
        if b.requests == 1 or b.ewma_latency_ms <= 0.0:
            b.ewma_latency_ms = lat
        else:
            b.ewma_latency_ms = (1.0 - alpha) * b.ewma_latency_ms + alpha * lat
        if error:
            b.errors += 1
        if self._shadow and backend != self._shadow:
            self._shadow_log.append({
                "primary": backend, "shadow": self._shadow,
                "latency_ms": lat, "timestamp_ns": time.time_ns(),
            })

    def auto_rebalance(
        self,
        max_error_rate: float = 0.1,
        *,
        max_latency_ms: float = 0.0,
        recover: bool = False,
    ) -> List[Dict[str, Any]]:
        """Shift weight away from backends breaching error/latency thresholds and optionally recover healthy ones."""
        actions: List[Dict[str, Any]] = []
        for b in self._backends.values():
            if b.requests < 20 or b.weight <= 0:
                continue
            obs_lat = b.ewma_latency_ms if b.ewma_latency_ms > 0.0 else b.mean_latency()
            if b.error_rate() > max_error_rate:
                old = b.weight
                b.weight = max(1, b.weight // 2)
                actions.append({"backend": b.name, "old_weight": old, "new_weight": b.weight, "reason": "high_error_rate"})
            elif max_latency_ms > 0.0 and obs_lat > max_latency_ms:
                old = b.weight
                b.weight = max(1, int(b.weight * 0.7))
                if b.weight != old:
                    actions.append({"backend": b.name, "old_weight": old, "new_weight": b.weight, "reason": "high_latency"})
            elif recover and b.healthy and b.weight < b.base_weight and b.error_rate() <= max_error_rate * 0.5:
                if max_latency_ms <= 0.0 or obs_lat <= max_latency_ms * 0.8:
                    old = b.weight
                    step = max(1, (b.base_weight - b.weight) // 2)
                    b.weight = min(b.base_weight, b.weight + step)
                    if b.weight != old:
                        actions.append({"backend": b.name, "old_weight": old, "new_weight": b.weight, "reason": "recovered"})
        return actions

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "traffic-splitter-card",
            "backends": {n: b.to_dict() for n, b in self._backends.items()},
            "sticky_sessions": len(self._sticky),
            "shadow": self._shadow,
            "shadow_events": len(self._shadow_log),
        }
