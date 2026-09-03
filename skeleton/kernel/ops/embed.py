"""Embedding table. Rows are token vectors. House dialect ids only."""
from __future__ import annotations

from typing import Dict, List

from skeleton.kernel.ops._stat import bump


class Embed:
    def __init__(self, d: int = 8) -> None:
        self.d = max(4, int(d))
        self.table: Dict[str, List[float]] = {}

    def row(self, tok: str) -> List[float]:
        if tok not in self.table:
            h = abs(hash(tok))
            self.table[tok] = [((h >> (i * 3)) & 7) / 7.0 * 2 - 1 for i in range(self.d)]
        bump(self.d)
        return list(self.table[tok])

    def card(self):
        return {"kind": "kernel-embed", "rows": len(self.table), "d": self.d, "stored_prose": 0}
