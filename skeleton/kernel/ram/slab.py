"""Slab allocator for fixed-size atoms.

One slab = width slots. Empty slabs go back to the buddy.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Slab:
    def __init__(self, width: int = 8, limit: int = 16) -> None:
        self.width = max(2, int(width))
        self.limit = max(1, int(limit))
        self.slabs: List[List[Optional[str]]] = []
        self.live = 0
        self.full_hits = 0

    def put(self, key: str) -> Optional[int]:
        for i, slab in enumerate(self.slabs):
            for j, slot in enumerate(slab):
                if slot is None:
                    slab[j] = str(key)
                    self.live += 1
                    return i * self.width + j
        if len(self.slabs) >= self.limit:
            self.full_hits += 1
            return None
        row: List[Optional[str]] = [None] * self.width
        row[0] = str(key)
        self.slabs.append(row)
        self.live += 1
        return (len(self.slabs) - 1) * self.width

    def drop(self, idx: int) -> None:
        i, j = divmod(int(idx), self.width)
        if i < len(self.slabs) and self.slabs[i][j] is not None:
            self.slabs[i][j] = None
            self.live -= 1

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-slab",
            "slabs": len(self.slabs),
            "live": self.live,
            "full": self.full_hits,
            "stored_prose": 0,
        }
