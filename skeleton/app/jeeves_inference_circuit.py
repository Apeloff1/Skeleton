"""Bounded local inference circuit breaker with a deterministic recovery probe.

This is process-local protective admission, not a durable transcript authority.
A circuit trips only after an actual native/GGUF execution failure, not for a
malformed request, an explicit cancellation, or a rejected remote provider.
A previously committed SQLite conversation remains readable when it is open.

No prompts, paths, exception strings, bearer tokens or model bytes are stored.
"""
from __future__ import annotations

from collections import deque
import math
import threading
import time
from typing import Callable


class LocalInferenceCircuit:
    """Thread-safe, bounded sliding-window failure admission for one local model.

    A recovery probe is the first *new* execution after the cooldown expires.
    The enclosing HTTP application already admits one generation at a time,
    so the probe does not race another local execution within the process.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        window_seconds: int = 60,
        cooldown_seconds: int = 10,
        maximum_cooldown_seconds: int = 120,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if (
            type(failure_threshold) is not int or not 2 <= failure_threshold <= 20
            or type(window_seconds) is not int or not 5 <= window_seconds <= 3600
            or type(cooldown_seconds) is not int or not 1 <= cooldown_seconds <= 3600
            or type(maximum_cooldown_seconds) is not int
            or not cooldown_seconds <= maximum_cooldown_seconds <= 3600
            or (clock is not None and not callable(clock))
        ):
            raise ValueError("invalid bounded local inference circuit policy")
        self._threshold = failure_threshold
        self._window = window_seconds
        self._initial_cooldown = cooldown_seconds
        self._maximum_cooldown = maximum_cooldown_seconds
        self._next_cooldown = cooldown_seconds
        self._clock = clock if clock is not None else time.monotonic
        self._lock = threading.RLock()
        self._failures: deque[float] = deque(maxlen=failure_threshold)
        self._open_until = 0.0
        self._tripped = False

    def _prune(self, now: float) -> None:
        while self._failures and now - self._failures[0] >= self._window:
            self._failures.popleft()

    def record_failure(self) -> None:
        """Count only actual backend/runtime execution failures."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            self._failures.append(now)
            if len(self._failures) >= self._threshold:
                self._tripped = True
                self._open_until = now + self._next_cooldown
                self._next_cooldown = min(
                    self._maximum_cooldown,
                    max(self._next_cooldown + 1, self._next_cooldown * 2),
                )

    def record_success(self) -> None:
        """A complete execution resets the circuit; replay is not a probe."""
        with self._lock:
            self._failures.clear()
            self._open_until = 0.0
            self._tripped = False
            self._next_cooldown = self._initial_cooldown

    def status(self) -> dict[str, int | str | bool]:
        """Privacy-safe, monotonic-time status without exception details."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            remaining = max(0.0, self._open_until - now)
            state = (
                "open" if remaining > 0
                else "probe_ready" if self._tripped
                else "closed"
            )
            return {
                "state": state,
                "admit_new_inference": state != "open",
                "recent_runtime_failures": len(self._failures),
                "failure_threshold": self._threshold,
                "retry_after_seconds": math.ceil(remaining),
                "window_seconds": self._window,
                "next_cooldown_seconds": self._next_cooldown,
            }


__all__ = ["LocalInferenceCircuit"]
