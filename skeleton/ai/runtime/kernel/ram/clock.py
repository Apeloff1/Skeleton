"""Clock / second-chance eviction over a circular frame table."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Clock:
    def __init__(self, frames: int = 32) -> None:
        n = max(4, int(frames))
        self.keys: List[Optional[str]] = [None] * n
        self.ref: List[int] = [0] * n
        self.hand = 0
        self.faults = 0
        self.evicts = 0

    def touch(self, key: str) -> int:
        key = str(key)
        if key in self.keys:
            i = self.keys.index(key)
            self.ref[i] = 1
            return i
        for _ in range(len(self.keys) * 2):
            i = self.hand
            self.hand = (self.hand + 1) % len(self.keys)
            if self.keys[i] is None:
                self.keys[i] = key
                self.ref[i] = 1
                self.faults += 1
                return i
            if self.ref[i] == 0:
                self.keys[i] = key
                self.ref[i] = 1
                self.evicts += 1
                self.faults += 1
                return i
            self.ref[i] = 0
        return 0

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-clock",
            "live": sum(1 for k in self.keys if k),
            "faults": self.faults,
            "evicts": self.evicts,
            "stored_prose": 0,
        }
