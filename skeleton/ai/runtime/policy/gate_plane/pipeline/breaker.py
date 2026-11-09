"""Circuit breaker for Pack F service-to-service calls.

Classic three-state breaker with two trip conditions:

* ``consecutive_failures`` failures in a row, or
* a failure rate of at least ``failure_rate`` over the last ``window_size``
  calls once ``min_calls`` have been observed.

``OPEN`` rejects immediately (``BreakerOpenError`` with ``retry_after_s`` set
to the remaining cool-down). After ``cooldown_s`` the breaker moves to
``HALF_OPEN`` lazily on the next :meth:`CircuitBreaker.try_acquire`, which
lets at most ``half_open_max_calls`` probes through. ``success_threshold``
probe successes close it; any probe failure re-opens it with a fresh
cool-down (optionally grown by ``cooldown_multiplier`` up to
``max_cooldown_s`` so a flapping upstream is probed less often).

Every transition is reported to listeners as ``(name, old, new)``; listener
exceptions are swallowed so observability can never change a verdict.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional

from skeleton.gate_plane.pipeline.errors import BreakerOpenError
from skeleton.gate_plane.s2s.clock import Clock, system_clock


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class BreakerConfig:
    consecutive_failures: int = 5
    failure_rate: float = 0.5
    window_size: int = 20
    min_calls: int = 10
    cooldown_s: float = 30.0
    cooldown_multiplier: float = 1.0
    max_cooldown_s: float = 300.0
    half_open_max_calls: int = 1
    success_threshold: int = 1

    def __post_init__(self) -> None:
        if self.consecutive_failures < 1:
            raise ValueError("consecutive_failures must be >= 1")
        if not 0.0 < self.failure_rate <= 1.0:
            raise ValueError("failure_rate must be within (0, 1]")
        if self.window_size < 1 or self.min_calls < 1:
            raise ValueError("window_size and min_calls must be >= 1")
        if self.min_calls > self.window_size:
            raise ValueError("min_calls cannot exceed window_size")
        if self.cooldown_s <= 0 or self.max_cooldown_s < self.cooldown_s:
            raise ValueError("need 0 < cooldown_s <= max_cooldown_s")
        if self.cooldown_multiplier < 1.0:
            raise ValueError("cooldown_multiplier must be >= 1")
        if self.half_open_max_calls < 1 or self.success_threshold < 1:
            raise ValueError("half_open_max_calls and success_threshold must be >= 1")
        if self.success_threshold > self.half_open_max_calls:
            raise ValueError("success_threshold cannot exceed half_open_max_calls")

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


TransitionListener = Callable[[str, BreakerState, BreakerState], None]


class CircuitBreaker:
    """Thread-safe circuit breaker driven by an injectable clock."""

    def __init__(
        self,
        name: str,
        config: Optional[BreakerConfig] = None,
        *,
        clock: Optional[Clock] = None,
        listeners: Optional[List[TransitionListener]] = None,
    ) -> None:
        self.name = name
        self.config = config or BreakerConfig()
        self._clock = clock or system_clock()
        self._listeners: List[TransitionListener] = list(listeners or [])
        self._lock = threading.Lock()
        self._state = BreakerState.CLOSED
        self._window: Deque[bool] = deque(maxlen=self.config.window_size)
        self._consecutive = 0
        self._opened_at = 0.0
        self._current_cooldown = self.config.cooldown_s
        self._probes_in_flight = 0
        self._probe_successes = 0
        self._counts = {"success": 0, "failure": 0, "rejected": 0, "ignored": 0, "opened": 0}
        self._transitions: List[Dict[str, Any]] = []

    # -- listeners -----------------------------------------------------------------
    def add_listener(self, listener: TransitionListener) -> None:
        self._listeners.append(listener)

    def _notify(self, pending: List[tuple]) -> None:
        for old, new in pending:
            for listener in list(self._listeners):
                try:
                    listener(self.name, old, new)
                except Exception:  # noqa: BLE001 - observers never change verdicts
                    pass

    # -- state machine (call with lock held) ----------------------------------------
    def _transition(self, new: BreakerState, pending: List[tuple]) -> None:
        old = self._state
        if old is new:
            return
        self._state = new
        now = self._clock.monotonic()
        if new is BreakerState.OPEN:
            if old is BreakerState.HALF_OPEN:
                self._current_cooldown = min(
                    self.config.max_cooldown_s, self._current_cooldown * self.config.cooldown_multiplier
                )
            else:
                self._current_cooldown = self.config.cooldown_s
            self._opened_at = now
            self._counts["opened"] += 1
        if new is BreakerState.HALF_OPEN:
            self._probes_in_flight = 0
            self._probe_successes = 0
        if new is BreakerState.CLOSED:
            self._window.clear()
            self._consecutive = 0
            self._current_cooldown = self.config.cooldown_s
        self._transitions.append({"at": now, "from": old.value, "to": new.value})
        if len(self._transitions) > 256:
            del self._transitions[:-256]
        pending.append((old, new))

    def _refresh(self, pending: List[tuple]) -> None:
        if self._state is BreakerState.OPEN and self._clock.monotonic() - self._opened_at >= self._current_cooldown:
            self._transition(BreakerState.HALF_OPEN, pending)

    def _should_trip(self) -> bool:
        if self._consecutive >= self.config.consecutive_failures:
            return True
        n = len(self._window)
        if n >= self.config.min_calls:
            failures = sum(1 for ok in self._window if not ok)
            return failures / n >= self.config.failure_rate
        return False

    # -- public API ----------------------------------------------------------------
    @property
    def state(self) -> BreakerState:
        pending: List[tuple] = []
        with self._lock:
            self._refresh(pending)
            state = self._state
        self._notify(pending)
        return state

    def retry_after_s(self) -> float:
        with self._lock:
            if self._state is not BreakerState.OPEN:
                return 0.0
            return round(max(0.0, self._opened_at + self._current_cooldown - self._clock.monotonic()), 2)

    def try_acquire(self) -> bool:
        """Ask for a call permit. Every ``True`` must be followed by exactly one
        of :meth:`record_success`, :meth:`record_failure` or :meth:`record_ignored`."""
        pending: List[tuple] = []
        with self._lock:
            self._refresh(pending)
            if self._state is BreakerState.CLOSED:
                allowed = True
            elif self._state is BreakerState.HALF_OPEN and self._probes_in_flight < self.config.half_open_max_calls:
                self._probes_in_flight += 1
                allowed = True
            else:
                self._counts["rejected"] += 1
                allowed = False
        self._notify(pending)
        return allowed

    def acquire(self) -> None:
        """Like :meth:`try_acquire` but raises :class:`BreakerOpenError`."""
        if not self.try_acquire():
            raise BreakerOpenError(self.name, retry_after_s=self.retry_after_s())

    def record_success(self) -> None:
        pending: List[tuple] = []
        with self._lock:
            self._counts["success"] += 1
            if self._state is BreakerState.HALF_OPEN:
                self._probes_in_flight = max(0, self._probes_in_flight - 1)
                self._probe_successes += 1
                if self._probe_successes >= self.config.success_threshold:
                    self._transition(BreakerState.CLOSED, pending)
            elif self._state is BreakerState.CLOSED:
                self._window.append(True)
                self._consecutive = 0
            # OPEN: a late success from a call admitted before the trip is ignored.
        self._notify(pending)

    def record_failure(self) -> None:
        pending: List[tuple] = []
        with self._lock:
            self._counts["failure"] += 1
            if self._state is BreakerState.HALF_OPEN:
                self._probes_in_flight = max(0, self._probes_in_flight - 1)
                self._transition(BreakerState.OPEN, pending)
            elif self._state is BreakerState.CLOSED:
                self._window.append(False)
                self._consecutive += 1
                if self._should_trip():
                    self._transition(BreakerState.OPEN, pending)
        self._notify(pending)

    def record_ignored(self) -> None:
        """Release a permit without counting the call (e.g. a 4xx or a cancel)."""
        with self._lock:
            self._counts["ignored"] += 1
            if self._state is BreakerState.HALF_OPEN:
                self._probes_in_flight = max(0, self._probes_in_flight - 1)

    def force_open(self) -> None:
        pending: List[tuple] = []
        with self._lock:
            self._transition(BreakerState.OPEN, pending)
        self._notify(pending)

    def reset(self) -> None:
        pending: List[tuple] = []
        with self._lock:
            self._transition(BreakerState.CLOSED, pending)
            self._window.clear()
            self._consecutive = 0
        self._notify(pending)

    def stats(self) -> Dict[str, Any]:
        pending: List[tuple] = []
        with self._lock:
            self._refresh(pending)
            n = len(self._window)
            failures = sum(1 for ok in self._window if not ok)
            out = {
                "name": self.name,
                "state": self._state.value,
                "window_calls": n,
                "window_failure_rate": round(failures / n, 4) if n else 0.0,
                "consecutive_failures": self._consecutive,
                "cooldown_s": self._current_cooldown,
                "probes_in_flight": self._probes_in_flight,
                **self._counts,
                "transitions": list(self._transitions[-16:]),
            }
        self._notify(pending)
        return out


class BreakerRegistry:
    """One breaker per upstream name, created on first use."""

    def __init__(self, *, clock: Optional[Clock] = None, default: Optional[BreakerConfig] = None) -> None:
        self._clock = clock or system_clock()
        self._default = default or BreakerConfig()
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._listeners: List[TransitionListener] = []
        self._lock = threading.Lock()

    def add_listener(self, listener: TransitionListener) -> None:
        with self._lock:
            self._listeners.append(listener)
            breakers = list(self._breakers.values())
        for b in breakers:
            b.add_listener(listener)

    def get(self, name: str, config: Optional[BreakerConfig] = None) -> CircuitBreaker:
        with self._lock:
            breaker = self._breakers.get(name)
            if breaker is None:
                breaker = CircuitBreaker(name, config or self._default, clock=self._clock, listeners=list(self._listeners))
                self._breakers[name] = breaker
            return breaker

    def states(self) -> Dict[str, str]:
        with self._lock:
            items = list(self._breakers.items())
        return {name: b.state.value for name, b in sorted(items)}

    def stats(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            items = list(self._breakers.items())
        return {name: b.stats() for name, b in sorted(items)}


__all__ = ["BreakerConfig", "BreakerRegistry", "BreakerState", "CircuitBreaker", "TransitionListener"]
