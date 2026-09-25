"""Retrieval plane health, latency telemetry, and bounded circuit breaking.

Circuit state is deliberately operational, not durable authority. It is derived
from live failures and latency. Cache identity includes the current circuit
state so a plane becoming unavailable/available cannot reuse rankings from a
different health topology.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Dict, Iterable, Optional


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


class PlaneCircuitOpen(RuntimeError):
    """A retrieval plane is temporarily isolated after repeated failures."""


@dataclass(frozen=True, slots=True)
class PlaneHealth:
    plane: str
    attempts: int
    successes: int
    failures: int
    consecutive_failures: int
    ewma_latency_ms: float
    last_error: str
    opened_at: Optional[float]
    open_until: Optional[float]

    def is_open(self, now: float) -> bool:
        return self.open_until is not None and now < self.open_until

    def to_dict(self, *, now: float) -> Dict[str, Any]:
        return {
            "plane": self.plane,
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "ewma_latency_ms": round(self.ewma_latency_ms, 3),
            "last_error": self.last_error,
            "circuit_open": self.is_open(now),
            "opened_at": self.opened_at,
            "open_until": self.open_until,
        }


class PlaneHealthTracker:
    """Thread-safe per-plane health with deterministic circuit transitions."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_s: float = 30.0,
        ewma_alpha: float = 0.2,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            isinstance(failure_threshold, bool)
            or not isinstance(failure_threshold, int)
            or failure_threshold < 1
        ):
            raise ValueError("failure_threshold must be a positive integer")
        cooldown = _finite("cooldown_s", cooldown_s)
        alpha = _finite("ewma_alpha", ewma_alpha)
        if cooldown <= 0:
            raise ValueError("cooldown_s must be positive")
        if not 0.0 < alpha <= 1.0:
            raise ValueError("ewma_alpha must be in (0, 1]")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown
        self.ewma_alpha = alpha
        self._clock = clock
        self._states: Dict[str, PlaneHealth] = {}
        self._revision = 0
        self._lock = RLock()

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def _default(self, plane: str) -> PlaneHealth:
        return PlaneHealth(
            plane=plane,
            attempts=0,
            successes=0,
            failures=0,
            consecutive_failures=0,
            ewma_latency_ms=0.0,
            last_error="",
            opened_at=None,
            open_until=None,
        )

    def state(self, plane: str) -> PlaneHealth:
        with self._lock:
            return self._states.get(plane, self._default(plane))

    def reset(self, plane: str) -> None:
        """Forget operational health when a retriever implementation is replaced."""
        with self._lock:
            if plane in self._states:
                del self._states[plane]
                self._revision += 1

    def before_call(self, plane: str) -> None:
        with self._lock:
            now = self._clock()
            current = self._states.get(plane, self._default(plane))
            if current.is_open(now):
                raise PlaneCircuitOpen(
                    f"retrieval plane {plane!r} circuit open until {current.open_until}"
                )
            if current.open_until is not None and now >= current.open_until:
                current = PlaneHealth(
                    plane=plane,
                    attempts=current.attempts,
                    successes=current.successes,
                    failures=current.failures,
                    consecutive_failures=0,
                    ewma_latency_ms=current.ewma_latency_ms,
                    last_error=current.last_error,
                    opened_at=None,
                    open_until=None,
                )
                self._states[plane] = current
                self._revision += 1

    def record_success(self, plane: str, latency_ms: float) -> PlaneHealth:
        latency = _finite("latency_ms", latency_ms)
        if latency < 0:
            raise ValueError("latency_ms must be non-negative")
        with self._lock:
            current = self._states.get(plane, self._default(plane))
            ewma = (
                latency
                if current.attempts == 0
                else (
                    self.ewma_alpha * latency
                    + (1.0 - self.ewma_alpha) * current.ewma_latency_ms
                )
            )
            updated = PlaneHealth(
                plane=plane,
                attempts=current.attempts + 1,
                successes=current.successes + 1,
                failures=current.failures,
                consecutive_failures=0,
                ewma_latency_ms=ewma,
                last_error="",
                opened_at=None,
                open_until=None,
            )
            self._states[plane] = updated
            self._revision += 1
            return updated

    def record_failure(
        self,
        plane: str,
        latency_ms: float,
        error: BaseException,
    ) -> PlaneHealth:
        latency = _finite("latency_ms", latency_ms)
        if latency < 0:
            raise ValueError("latency_ms must be non-negative")
        with self._lock:
            now = self._clock()
            current = self._states.get(plane, self._default(plane))
            consecutive = current.consecutive_failures + 1
            ewma = (
                latency
                if current.attempts == 0
                else (
                    self.ewma_alpha * latency
                    + (1.0 - self.ewma_alpha) * current.ewma_latency_ms
                )
            )
            opens = consecutive >= self.failure_threshold
            updated = PlaneHealth(
                plane=plane,
                attempts=current.attempts + 1,
                successes=current.successes,
                failures=current.failures + 1,
                consecutive_failures=consecutive,
                ewma_latency_ms=ewma,
                last_error=type(error).__name__,
                opened_at=now if opens else None,
                open_until=(now + self.cooldown_s) if opens else None,
            )
            self._states[plane] = updated
            self._revision += 1
            return updated

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            now = self._clock()
            return {
                plane: state.to_dict(now=now)
                for plane, state in sorted(self._states.items())
            }

    def cache_token(self, planes: Iterable[str] = ()) -> str:
        """Hash only ranking-relevant open/closed circuit topology."""
        requested = tuple(sorted(set(planes)))
        with self._lock:
            now = self._clock()
            names = sorted(set(requested) | set(self._states))
            rows = [
                (
                    plane,
                    self._states.get(plane, self._default(plane)).is_open(now),
                )
                for plane in names
            ]
        encoded = json.dumps(
            {"circuits": rows},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.blake2b(encoded, digest_size=12).hexdigest()
