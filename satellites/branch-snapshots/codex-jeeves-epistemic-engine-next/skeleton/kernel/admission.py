"""Admission kernel — frequency + recency gate.

Pointer: TinyLFU-style sketch. House mapping is a 256-bin count
sketch plus a tiny window. No paper operators imported.
"""
from __future__ import annotations

from typing import Any, Dict, Hashable


class Admission:
    def __init__(self, bins: int = 256, window: int = 32) -> None:
        self.bins = max(16, int(bins))
        self.window = max(4, int(window))
        self.freq = [0] * self.bins
        self.seen: list = []
        self.admitted = 0
        self.denied = 0

    def _bin(self, key: Hashable) -> int:
        return hash(key) % self.bins

    def offer(self, key: Hashable) -> bool:
        i = self._bin(key)
        self.freq[i] += 1
        self.seen.append(key)
        if len(self.seen) > self.window:
            old = self.seen.pop(0)
            self.freq[self._bin(old)] = max(0, self.freq[self._bin(old)] - 1)
        ok = self.freq[i] >= 2 or len(self.seen) < self.window // 2
        if ok:
            self.admitted += 1
        else:
            self.denied += 1
        return ok

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-admission",
            "admitted": self.admitted,
            "denied": self.denied,
            "window": self.window,
            "stored_prose": 0,
        }
