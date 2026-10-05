"""Throttle kernel — token bucket on pulses.

Mobile overlay uses a smaller rate. Never an unbounded write.
"""
from __future__ import annotations

import time
from typing import Any, Dict


class Throttle:
    def __init__(self, rate: float = 4.0, burst: float = 8.0) -> None:
        self.rate = max(0.25, float(rate))
        self.burst = max(1.0, float(burst))
        self.tokens = self.burst
        self.ts = time.monotonic()
        self.allowed = 0
        self.blocked = 0

    def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        self.tokens = min(self.burst, self.tokens + (now - self.ts) * self.rate)
        self.ts = now
        if self.tokens >= cost:
            self.tokens -= cost
            self.allowed += 1
            return True
        self.blocked += 1
        return False

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-throttle",
            "rate": self.rate,
            "tokens": round(self.tokens, 3),
            "allowed": self.allowed,
            "blocked": self.blocked,
            "stored_prose": 0,
        }
