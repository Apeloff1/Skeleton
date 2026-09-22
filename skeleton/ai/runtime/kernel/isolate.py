"""Isolate kernel — recallable grant for a mouth slot.

Pointer: FlexServe recallable isolation. House mapping is a
lease-like grant that the normal path can reclaim under pressure.
No TrustZone. No NPU claim.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class Isolate:
    def __init__(self) -> None:
        self.held: Dict[str, Dict[str, Any]] = {}
        self.recalled = 0

    def grant(self, slot: str, *, atoms: int = 16) -> Dict[str, Any]:
        row = {"slot": slot, "atoms": int(atoms), "live": 1}
        self.held[slot] = row
        return row

    def recall(self, slot: str = "") -> int:
        n = 0
        if slot:
            if self.held.pop(slot, None):
                n = 1
        else:
            n = len(self.held)
            self.held.clear()
        self.recalled += n
        return n

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-isolate",
            "held": len(self.held),
            "recalled": self.recalled,
            "stored_prose": 0,
        }
