"""adaptive_gate — token-bucket priority admission (gameforge-rs AdaptiveGate).

High-priority / control-plane traffic (priority 0) may overdraw when the
bucket is empty; bulk traffic (priority > 0) sheds first.

Separate from ``skeleton.kernel.backpressure`` (bus TokenBucket /
LoadShedder / BackpressureGovernor) — that module is left untouched.
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Dict


class Verdict(Enum):
    ADMITTED = "admitted"
    SHED = "shed"


class AdaptiveGate:
    """Sync token bucket + priority admission. Port of gf ``backpressure::AdaptiveGate``."""

    def __init__(self, capacity: int, refill_per_sec: int) -> None:
        if capacity < 0 or refill_per_sec < 0:
            raise ValueError("capacity and refill_per_sec must be non-negative")
        self._capacity = int(capacity)
        self._refill_per_sec = int(refill_per_sec)
        self._tokens = int(capacity)
        self._admitted = 0
        self._shed = 0
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill_unlocked(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        add = int(elapsed * self._refill_per_sec)
        if add > 0:
            self._tokens = min(self._tokens + add, self._capacity)
            self._last_refill = now

    def admit(self, priority: int) -> Verdict:
        with self._lock:
            self._refill_unlocked()
            # Priority 0 (control plane) may still admit when tokens==0 (overdraw).
            if self._tokens == 0 and priority > 0:
                self._shed += 1
                return Verdict.SHED
            if self._tokens > 0:
                self._tokens -= 1
            # else: priority 0 overdraw — leave tokens at 0
            self._admitted += 1
            return Verdict.ADMITTED

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "tokens_available": self._tokens,
                "capacity": self._capacity,
                "admitted": self._admitted,
                "shed": self._shed,
            }
