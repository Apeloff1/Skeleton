"""Map reveal system.
Tracks explored rooms and fog of war based on progress and optical.
"""
from __future__ import annotations
from typing import Any, Dict, List, Set

class MapReveal:
    def __init__(self):
        self.revealed: Set[int] = set()
    def explore(self, room_id: int, optical: float = 0.9) -> None:
        self.revealed.add(room_id)
        if optical > 0.92:
            self.revealed.add(room_id + 1)
            self.revealed.add(room_id - 1)
    def fog(self, total_rooms: int = 12) -> Dict[str, Any]:
        return {
            "revealed": sorted(self.revealed),
            "hidden": [i for i in range(total_rooms) if i not in self.revealed],
            "percent": round(len(self.revealed) / max(1, total_rooms), 2),
        }
