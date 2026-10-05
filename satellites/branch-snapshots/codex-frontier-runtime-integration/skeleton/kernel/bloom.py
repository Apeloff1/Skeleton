"""Bloom kernel — membership for dump/index keys. No false-negative."""
from __future__ import annotations

from typing import Any, Dict, Hashable


class Bloom:
    def __init__(self, bits: int = 2048, k: int = 3) -> None:
        self.n = max(64, int(bits))
        self.k = max(1, min(8, int(k)))
        self.bits = [0] * self.n
        self.n_add = 0

    def _hashes(self, key: Hashable):
        h = hash(key)
        for i in range(self.k):
            yield (h + i * 0x9E3779B9) % self.n

    def add(self, key: Hashable) -> None:
        for i in self._hashes(key):
            self.bits[i] = 1
        self.n_add += 1

    def has(self, key: Hashable) -> bool:
        return all(self.bits[i] for i in self._hashes(key))

    def card(self) -> Dict[str, Any]:
        filled = sum(self.bits)
        return {
            "kind": "kernel-bloom",
            "bits": self.n,
            "filled": filled,
            "added": self.n_add,
            "load": round(filled / self.n, 4),
            "stored_prose": 0,
        }
