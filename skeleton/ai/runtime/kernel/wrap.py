"""Adapters so in-tree breaker/bulkhead speak card()."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.breaker import CircuitBreaker
from skeleton.kernel.bulkhead import BulkheadRegistry


class BreakerCard:
    def __init__(self, *, mobile: bool = True) -> None:
        self.inner = CircuitBreaker(
            "ops",
            failure_threshold=3 if mobile else 5,
            cooldown_s=5.0 if mobile else 10.0,
        )

    def card(self) -> Dict[str, Any]:
        state = getattr(self.inner, "state", None)
        return {
            "kind": "kernel-breaker",
            "name": self.inner.name,
            "state": str(state.name if state is not None else "closed"),
            "stored_prose": 0,
        }


class BulkheadCard:
    def __init__(self, *, mobile: bool = True) -> None:
        self.inner = BulkheadRegistry(4 if mobile else 16, system_reserve=1)
        self.mobile = mobile

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-bulkhead",
            "mobile": int(self.mobile),
            "stored_prose": 0,
        }
