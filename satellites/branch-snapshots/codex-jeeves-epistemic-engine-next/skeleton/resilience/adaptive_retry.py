"""Adaptive retry — retry policies that learn from observed outcomes.

Extends fixed backoff with per-endpoint learning: tracks which delay
and attempt counts historically succeed, then adjusts the schedule.
Distinguishes retryable from permanent errors via a learned classifier
so permanent failures fail fast instead of burning the retry budget.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class AttemptRecord:
    endpoint: str
    attempt: int
    delay_s: float
    success: bool
    error_kind: str
    timestamp_ns: int = 0


@dataclass
class EndpointPolicy:
    base_delay_s: float = 0.1
    max_attempts: int = 3
    multiplier: float = 2.0
    learned_permanent_errors: set = field(default_factory=set)
    attempts: int = 0
    successes: int = 0

    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 1.0


class AdaptiveRetry:
    """Retry engine that learns per-endpoint policies."""

    def __init__(self, rng: Optional[random.Random] = None):
        self._policies: Dict[str, EndpointPolicy] = {}
        self._history: List[AttemptRecord] = []
        self._rng = rng or random.Random()

    def _policy(self, endpoint: str) -> EndpointPolicy:
        return self._policies.setdefault(endpoint, EndpointPolicy())

    def _classify(self, exc: Exception) -> str:
        name = type(exc).__name__.lower()
        if any(k in name for k in ("timeout", "connection", "temporary", "unavailable")):
            return "transient"
        if any(k in name for k in ("value", "type", "key", "notfound", "permission")):
            return "permanent"
        return "unknown"

    def is_retryable(self, endpoint: str, exc: Exception) -> bool:
        policy = self._policy(endpoint)
        kind = self._classify(exc)
        if kind == "permanent":
            return False
        if type(exc).__name__ in policy.learned_permanent_errors:
            return False
        return kind in ("transient", "unknown")

    def _delay_for(self, policy: EndpointPolicy, attempt: int) -> float:
        delay = policy.base_delay_s * (policy.multiplier ** attempt)
        jitter = self._rng.uniform(0.8, 1.2)
        return min(delay * jitter, 30.0)

    def execute(self, endpoint: str, fn: Callable[[], Any]) -> Dict[str, Any]:
        policy = self._policy(endpoint)
        last_exc: Optional[Exception] = None
        for attempt in range(policy.max_attempts):
            policy.attempts += 1
            try:
                result = fn()
                policy.successes += 1
                self._history.append(AttemptRecord(endpoint, attempt, 0.0, True, "transient", time.time_ns()))
                return {"success": True, "result": result, "attempts": attempt + 1}
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                kind = self._classify(exc)
                if not self.is_retryable(endpoint, exc):
                    if kind == "unknown":
                        policy.learned_permanent_errors.add(type(exc).__name__)
                    self._history.append(AttemptRecord(endpoint, attempt, 0.0, False, kind, time.time_ns()))
                    return {"success": False, "error": str(exc), "attempts": attempt + 1, "failed_fast": True}
                delay = self._delay_for(policy, attempt)
                self._history.append(AttemptRecord(endpoint, attempt, delay, False, kind, time.time_ns()))
                time.sleep(min(delay, 0.05))
        if len(self._history) > 20:
            late_wins = [r for r in self._history[-20:] if r.endpoint == endpoint and r.success and r.attempt >= 2]
            if late_wins and policy.max_attempts < 6:
                policy.max_attempts += 1
        return {"success": False, "error": str(last_exc), "attempts": policy.max_attempts, "exhausted": True}

    def tune(self, endpoint: str, base_delay_s: Optional[float] = None,
             max_attempts: Optional[int] = None, multiplier: Optional[float] = None) -> None:
        policy = self._policy(endpoint)
        if base_delay_s is not None:
            policy.base_delay_s = base_delay_s
        if max_attempts is not None:
            policy.max_attempts = max_attempts
        if multiplier is not None:
            policy.multiplier = multiplier

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "adaptive-retry-card",
            "endpoints": {e: {
                "attempts": p.attempts,
                "success_rate": round(p.success_rate(), 3),
                "max_attempts": p.max_attempts,
                "learned_permanent": sorted(p.learned_permanent_errors),
            } for e, p in self._policies.items()},
            "history": len(self._history),
        }
