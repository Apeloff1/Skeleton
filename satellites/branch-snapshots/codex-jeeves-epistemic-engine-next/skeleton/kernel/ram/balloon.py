"""Balloon — give frames back when pressure rises.

Linux balloon driver handle. House mapping: shrink the clock/slab
working set by a fraction of live frames.
"""
from __future__ import annotations

from typing import Any, Dict


class Balloon:
    def __init__(self) -> None:
        self.inflated = 0
        self.released = 0

    def inflate(self, clock, *, fraction: float = 0.25) -> int:
        live = [i for i, k in enumerate(clock.keys) if k]
        n = max(1, int(len(live) * max(0.0, min(0.9, fraction))))
        killed = 0
        for i in live[:n]:
            clock.keys[i] = None
            clock.ref[i] = 0
            killed += 1
        self.inflated += killed
        return killed

    def deflate(self, n: int = 0) -> int:
        self.released += int(n)
        return int(n)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-balloon",
            "inflated": self.inflated,
            "released": self.released,
            "stored_prose": 0,
        }
