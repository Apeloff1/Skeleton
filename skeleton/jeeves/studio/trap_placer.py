"""Trap placer.
Places and triggers environmental traps based on optical and room state.
"""
from __future__ import annotations
from typing import Any, Dict, List

class TrapPlacer:
    def __init__(self):
        self.traps: List[Dict[str, Any]] = []
    def place(self, room_id: int, kind: str = "spike", damage: int = 10) -> Dict[str, Any]:
        trap = {"room": room_id, "kind": kind, "damage": damage, "armed": True}
        self.traps.append(trap)
        return trap
    def trigger(self, room_id: int) -> List[Dict[str, Any]]:
        hit = []
        for t in self.traps:
            if t["room"] == room_id and t["armed"]:
                t["armed"] = False
                hit.append(t)
        return hit
    def active_count(self) -> int:
        return sum(1 for t in self.traps if t["armed"])
