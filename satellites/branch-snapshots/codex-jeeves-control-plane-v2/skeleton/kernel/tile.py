"""Tile kernel — residual/decode width cap."""
from __future__ import annotations

from typing import Any, Dict


class Tile:
    def __init__(self, width: int = 8) -> None:
        self.width = max(1, int(width))
        self.runs = 0
        self.clipped = 0

    def fit(self, n: int) -> int:
        n = max(0, int(n))
        if n > self.width:
            self.clipped += 1
            n = self.width
        self.runs += 1
        return n

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-tile",
            "width": self.width,
            "runs": self.runs,
            "clipped": self.clipped,
            "stored_prose": 0,
        }
