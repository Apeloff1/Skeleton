"""Prefix kernel — shared token-bag cache.

Pointer: prefix caching on paged KV. House mapping is exact prefix
of token tuples. No KV tensors.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


class Prefix:
    def __init__(self, cap: int = 32) -> None:
        self.cap = max(4, int(cap))
        self.store: Dict[Tuple[str, ...], int] = {}
        self.hits = 0
        self.miss = 0

    def look(self, tokens: Tuple[str, ...]) -> bool:
        key = tuple(tokens[:8])
        if key in self.store:
            self.hits += 1
            self.store[key] += 1
            return True
        self.miss += 1
        if len(self.store) >= self.cap:
            cold = min(self.store, key=self.store.get)
            del self.store[cold]
        self.store[key] = 1
        return False

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-prefix",
            "n": len(self.store),
            "hits": self.hits,
            "miss": self.miss,
            "stored_prose": 0,
        }
