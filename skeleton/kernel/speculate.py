"""Speculate kernel — draft length vs accept.

Pointer: speculative decoding. House mapping is K-draft budget
and an accept ratio. No draft model. K stays 2 on mobile, 4 desktop.
"""
from __future__ import annotations

from typing import Any, Dict


class Speculate:
    def __init__(self, k: int = 2) -> None:
        self.k = max(1, min(8, int(k)))
        self.drafted = 0
        self.accepted = 0

    def draft(self) -> int:
        self.drafted += self.k
        return self.k

    def accept(self, n: int) -> int:
        take = max(0, min(self.k, int(n)))
        self.accepted += take
        return take

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-speculate",
            "k": self.k,
            "drafted": self.drafted,
            "accepted": self.accepted,
            "ratio": round(self.accepted / max(1, self.drafted), 4),
            "stored_prose": 0,
        }
