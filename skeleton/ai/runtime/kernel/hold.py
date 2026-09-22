"""Hold — freeze the live roster. Drift stops a season."""
from __future__ import annotations

from typing import Any, Dict, Set


class Hold:
    def __init__(self) -> None:
        self.names: Set[str] = set()
        self.drifts = 0

    def latch(self, names) -> None:
        self.names = set(names)

    def check(self, names) -> bool:
        now = set(names)
        if not self.names:
            self.latch(now)
            return True
        if now != self.names:
            self.drifts += 1
            return False
        return True

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-hold",
            "n": len(self.names),
            "drifts": self.drifts,
            "stored_prose": 0,
        }
