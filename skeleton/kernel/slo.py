"""SLO kernel — miss budget against nervous targets."""
from __future__ import annotations

from typing import Any, Dict


class SLO:
    def __init__(self, miss_cap: int = 3) -> None:
        self.miss_cap = max(1, int(miss_cap))
        self.ok = 0
        self.miss = 0

    def record(self, good: bool) -> bool:
        if good:
            self.ok += 1
            return True
        self.miss += 1
        return self.miss < self.miss_cap

    def trip(self) -> bool:
        return self.miss >= self.miss_cap

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-slo",
            "ok": self.ok,
            "miss": self.miss,
            "trip": int(self.trip()),
            "stored_prose": 0,
        }
