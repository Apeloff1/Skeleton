"""Affinity kernel — pin a stimulus family to a mouth slot."""
from __future__ import annotations

from typing import Any, Dict, Optional


class Affinity:
    def __init__(self) -> None:
        self.pin: Dict[str, str] = {}
        self.hits = 0
        self.miss = 0

    def bind(self, family: str, slot: str) -> None:
        self.pin[str(family)] = str(slot)

    def slot(self, family: str, default: str = "right") -> str:
        found = self.pin.get(str(family))
        if found:
            self.hits += 1
            return found
        self.miss += 1
        return default

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-affinity",
            "pins": len(self.pin),
            "hits": self.hits,
            "miss": self.miss,
            "stored_prose": 0,
        }
