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


PRIORITY_TIERS: Dict[str, int] = {
    "critical": 0,
    "heavy": 1,
    "normal": 2,
    "background": 3,
    "shed_first": 4,
}


@dataclass
class Backend:
    name: str
    weight: int = 100
    healthy: bool = True
    requests: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    ewma_latency_ms: float = 0.0
    latency_slope_ms: float = 0.0
    quality_score: float = 1.0
    in_flight: int = 0
    max_concurrency: int = 0
    base_weight: int = 0
    circuit_state: str = "closed"
    consecutive_errors: int = 0
    circuit_trip_threshold: int = 5
    circuit_cooldown_ms: float = 5000.0
    circuit_opened_ns: int = 0
    half_open_successes: int = 0
    half_open_required_successes: int = 2
    rate_limit_rps: float = 0.0
    burst_capacity: float = 0.0
    _tokens: float = 0.0
    _last_refill_ns: int = 0

    def __post_init__(self) -> None:
        if self.base_weight <= 0:
            self.base_weight = max(1, int(self.weight))
        if self.rate_limit_rps > 0.0:
            if self.burst_capacity <= 0.0:
                self.burst_capacity = max(1.0, self.rate_limit_rps)
            self._tokens = self.burst_capacity
            self._last_refill_ns = time.time_ns()

    def error_rate(self) -> float:
        return self.errors / self.requests if self.requests else 0.0

    def mean_latency(self) -> float:
        return self.total_latency_ms / self.requests if self.requests else 0.0

    def _check_circuit(self) -> bool:
        if self.circuit_state == "open":
            elapsed_ms = (time.time_ns() - self.circuit_opened_ns) / 1e6
            if elapsed_ms >= self.circuit_cooldown_ms:
                self.circuit_state = "half_open"
                self.half_open_successes = 0
            else:
                return False
        if self.circuit_state == "half_open" and self.in_flight >= 1:
            return False
        return True

    def _consume_token(self) -> bool:
        if self.rate_limit_rps <= 0.0:
            return True
        now = time.time_ns()
        elapsed_s = max(0.0, (now - self._last_refill_ns) / 1e9)
        self._last_refill_ns = now
        cap = self.burst_capacity if self.burst_capacity > 0.0 else self.rate_limit_rps
        self._tokens = min(cap, self._tokens + elapsed_s * self.rate_limit_rps)
        if self._tokens < 1.0:
            return False
        self._tokens -= 1.0
        return True

    def has_capacity(self, *, priority: str = "normal") -> bool:
        if not self.healthy or self.weight <= 0:
            return False
        if not self._check_circuit():
            return False
        if self.max_concurrency > 0:
            if self.in_flight >= self.max_concurrency:
                return False
            util = float(self.in_flight) / float(self.max_concurrency)
            tier = PRIORITY_TIERS.get(str(priority).lower(), 2)
            if tier >= 3 and util >= 0.75:
                return False
            if tier == 2 and self.max_concurrency >= 4 and util >= 0.90:
                return False
        return True

    def effective_weight(self, *, latency_budget_ms: float = 0.0, priority: str = "normal") -> float:
        if not self.has_capacity(priority=priority):
            return 0.0
        reliability = max(0.05, 1.0 - min(0.95, self.error_rate()))
        if self.circuit_state == "half_open":
            reliability *= 0.25
        quality = max(0.05, float(self.quality_score))
        lat_factor = 1.0
        obs_lat = self.ewma_latency_ms if self.ewma_latency_ms > 0.0 else self.mean_latency()
        # Predictive latency projection using EWMA derivative (slope)
        projected_lat = max(0.0, obs_lat + max(0.0, self.latency_slope_ms) * 1.5)
        if latency_budget_ms > 0.0 and projected_lat > latency_budget_ms:
            lat_factor = 1.0 / (1.0 + (projected_lat - latency_budget_ms) / latency_budget_ms)
        elif self.latency_slope_ms > 10.0:
            lat_factor = 1.0 / (1.0 + self.latency_slope_ms / max(50.0, obs_lat))
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
            "circuit_state": self.circuit_state,
            "consecutive_errors": self.consecutive_errors,
            "requests": self.requests,
            "error_rate": round(self.error_rate(), 4),
            "mean_latency_ms": round(self.mean_latency(), 2),
            "ewma_latency_ms": round(self.ewma_latency_ms, 2),
            "latency_slope_ms": round(self.latency_slope_ms, 3),
            "quality_score": round(self.quality_score, 4),
            "in_flight": self.in_flight,
            "max_concurrency": self.max_concurrency,
        }


GAME_STAGE_LATENCY_BUDGETS_MS: Dict[str, float] = {
    "spec_compile": 40.0,
    "world_layout": 60.0,
    "encounter_sim": 80.0,
    "walk_proof": 90.0,
    "gdscript_repair": 150.0,
    "polish_rubric": 120.0,
    "self_learn_distill": 200.0,
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
        circuit_trip_threshold: int = 5,
        circuit_cooldown_ms: float = 5000.0,
        rate_limit_rps: float = 0.0,
        burst_capacity: float = 0.0,
    ) -> Backend:
        b = Backend(
            name=name,
            weight=weight,
            max_concurrency=max(0, int(max_concurrency)),
            quality_score=max(0.05, float(quality_score)),
            base_weight=max(1, int(weight)),
            circuit_trip_threshold=max(0, int(circuit_trip_threshold)),
            circuit_cooldown_ms=max(1.0, float(circuit_cooldown_ms)),
            rate_limit_rps=max(0.0, float(rate_limit_rps)),
            burst_capacity=max(0.0, float(burst_capacity)),
        )
        self._backends[name] = b
        return b

    def configure_circuit_breaker(
        self,
        name: str,
        *,
        trip_threshold: int = 5,
        cooldown_ms: float = 5000.0,
        half_open_required_successes: int = 2,
    ) -> None:
        if name in self._backends:
            b = self._backends[name]
            b.circuit_trip_threshold = max(0, int(trip_threshold))
            b.circuit_cooldown_ms = max(1.0, float(cooldown_ms))
            b.half_open_required_successes = max(1, int(half_open_required_successes))

    def configure_rate_limit(
        self,
        name: str,
        *,
        rate_limit_rps: float,
        burst_capacity: Optional[float] = None,
    ) -> None:
        if name in self._backends:
            b = self._backends[name]
            b.rate_limit_rps = max(0.0, float(rate_limit_rps))
            b.burst_capacity = float(burst_capacity) if burst_capacity is not None else max(1.0, b.rate_limit_rps)
            b._tokens = b.burst_capacity
            b._last_refill_ns = time.time_ns()

    def set_weight(self, name: str, weight: int) -> None:
        self._backends[name].weight = max(0, weight)
        if weight > 0:
            self._backends[name].base_weight = max(1, int(weight))

    def set_quality(self, name: str, quality_score: float) -> None:
        if name in self._backends:
            self._backends[name].quality_score = max(0.05, float(quality_score))

    def mark_health(self, name: str, healthy: bool) -> None:
        self._backends[name].healthy = healthy
        if healthy and self._backends[name].circuit_state == "open":
            self._backends[name].circuit_state = "closed"
            self._backends[name].consecutive_errors = 0

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
        priority: str = "normal",
    ) -> Optional[str]:
        if session_id and session_id in self._sticky:
            name = self._sticky[session_id]
            if name in self._backends and self._backends[name].has_capacity(priority=priority):
                if self._backends[name]._consume_token():
                    return name
        pool = [b for b in self._backends.values() if b.has_capacity(priority=priority)]
        if not pool:
            return None
        if latency_aware:
            weights = [b.effective_weight(latency_budget_ms=latency_budget_ms, priority=priority) for b in pool]
        else:
            weights = [float(b.weight) for b in pool]
        total = sum(weights)
        if total <= 0.0:
            return None
        roll = self._rng.uniform(0.0, total)
        acc = 0.0
        for b, w in zip(pool, weights):
            acc += w
            if roll <= acc and b._consume_token():
                if session_id:
                    self._sticky[session_id] = b.name
                return b.name
        for b in reversed(pool):
            if b._consume_token():
                if session_id:
                    self._sticky[session_id] = b.name
                return b.name
        return None

    def route_heavy_task(
        self,
        session_id: Optional[str] = None,
        *,
        latency_budget_ms: float = 150.0,
    ) -> Dict[str, Any]:
        """Select a primary backend and a distinct healthy backup backend for heavy tasks."""
        pool = [b for b in self._backends.values() if b.has_capacity(priority="heavy")]
        if not pool:
            return {"primary": None, "backup": None, "backup_available": False}
        ranked = sorted(
            pool,
            key=lambda b: b.effective_weight(latency_budget_ms=latency_budget_ms, priority="heavy"),
            reverse=True,
        )
        primary_b = None
        if session_id and session_id in self._sticky:
            sticky_name = self._sticky[session_id]
            for b in ranked:
                if b.name == sticky_name and b._consume_token():
                    primary_b = b
                    break
        if primary_b is None:
            for b in ranked:
                if b._consume_token():
                    primary_b = b
                    break
        if primary_b is None:
            return {"primary": None, "backup": None, "backup_available": False}
        if session_id:
            self._sticky[session_id] = primary_b.name
        backup_b = next((b for b in ranked if b.name != primary_b.name), None)
        return {
            "primary": primary_b.name,
            "backup": backup_b.name if backup_b is not None else None,
            "backup_available": backup_b is not None,
        }

    def acquire_route(
        self,
        session_id: Optional[str] = None,
        *,
        latency_aware: bool = True,
        latency_budget_ms: float = 100.0,
        priority: str = "normal",
    ) -> Optional[str]:
        chosen = self.route(
            session_id=session_id,
            latency_aware=latency_aware,
            latency_budget_ms=latency_budget_ms,
            priority=priority,
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

    def route_game_stage(
        self,
        stage: str,
        *,
        session_id: Optional[str] = None,
        remaining_deadline_s: Optional[float] = None,
    ) -> Optional[str]:
        """Route a game-creation stage with deadline-aware latency budgeting."""
        stage_budget = GAME_STAGE_LATENCY_BUDGETS_MS.get(str(stage or "").lower(), 100.0)
        if remaining_deadline_s is not None:
            rem_ms = max(5.0, float(remaining_deadline_s) * 1000.0 * 0.25)
            stage_budget = min(stage_budget, rem_ms)
        return self.route(
            session_id=session_id,
            latency_aware=True,
            latency_budget_ms=stage_budget,
        )

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
            b.latency_slope_ms = 0.0
        else:
            prev_ewma = b.ewma_latency_ms
            b.ewma_latency_ms = (1.0 - alpha) * b.ewma_latency_ms + alpha * lat
            inst_slope = b.ewma_latency_ms - prev_ewma
            b.latency_slope_ms = 0.7 * b.latency_slope_ms + 0.3 * inst_slope
        if error:
            b.errors += 1
            b.consecutive_errors += 1
            if b.circuit_state == "half_open" or (
                b.circuit_trip_threshold > 0 and b.consecutive_errors >= b.circuit_trip_threshold
            ):
                b.circuit_state = "open"
                b.circuit_opened_ns = time.time_ns()
                b.half_open_successes = 0
        else:
            b.consecutive_errors = 0
            if b.circuit_state == "half_open":
                b.half_open_successes += 1
                if b.half_open_successes >= b.half_open_required_successes:
                    b.circuit_state = "closed"
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

    def forecast_brownout(self, *, latency_budget_ms: float = 100.0, horizon_steps: int = 3) -> Dict[str, Any]:
        """Predict backend brownout risk over `horizon_steps` using EWMA latency + velocity slope."""
        at_risk: List[str] = []
        healthy_headroom: List[str] = []
        forecasts: Dict[str, Dict[str, Any]] = {}
        steps = max(1, int(horizon_steps))
        for name, b in self._backends.items():
            cur = b.ewma_latency_ms if b.ewma_latency_ms > 0.0 else b.mean_latency()
            predicted = max(0.0, cur + b.latency_slope_ms * steps)
            will_breach = bool(
                not b.healthy
                or b.circuit_state != "closed"
                or (latency_budget_ms > 0.0 and predicted > latency_budget_ms)
            )
            if will_breach:
                at_risk.append(name)
            else:
                healthy_headroom.append(name)
            forecasts[name] = {
                "current_ewma_ms": round(cur, 2),
                "slope_ms": round(b.latency_slope_ms, 3),
                "predicted_ms": round(predicted, 2),
                "will_breach_budget": will_breach,
            }
        return {
            "latency_budget_ms": latency_budget_ms,
            "horizon_steps": steps,
            "at_risk_backends": at_risk,
            "healthy_headroom_backends": healthy_headroom,
            "forecasts": forecasts,
        }
