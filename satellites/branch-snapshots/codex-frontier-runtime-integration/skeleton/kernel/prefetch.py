"""Prefetch kernel — warm the next itinerary code."""
from __future__ import annotations

from typing import Any, Dict, List


class Prefetch:
    def __init__(self, depth: int = 2) -> None:
        self.depth = max(1, int(depth))
        self.warm: List[str] = []
        self.hits = 0

    def load(self, queue: List[str]) -> List[str]:
        self.warm = [str(c) for c in (queue or [])[: self.depth]]
        return list(self.warm)

    def hit(self, code: str) -> bool:
        ok = str(code) in self.warm
        if ok:
            self.hits += 1
        return ok

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-prefetch",
            "depth": self.depth,
            "warm": list(self.warm),
            "hits": self.hits,
            "stored_prose": 0,
        }
