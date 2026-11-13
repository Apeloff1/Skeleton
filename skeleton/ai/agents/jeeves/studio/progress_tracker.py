"""Progress tracker.
Tracks rooms cleared, packs, boss phases, and overall completion percentage.
"""
from __future__ import annotations
from typing import Any, Dict

class ProgressTracker:
    def __init__(self, total_rooms: int = 12):
        self.total_rooms = total_rooms
        self.rooms_cleared = 0
        self.packs_cleared = 0
        self.boss_phase = 0
        self.boss_defeated = False
    def clear_room(self) -> None:
        self.rooms_cleared = min(self.total_rooms, self.rooms_cleared + 1)
    def clear_pack(self) -> None:
        self.packs_cleared += 1
    def advance_boss(self, phase: int, defeated: bool = False) -> None:
        self.boss_phase = phase
        self.boss_defeated = defeated
    def percent(self) -> float:
        room_p = self.rooms_cleared / max(1, self.total_rooms)
        boss_p = 1.0 if self.boss_defeated else self.boss_phase / 5.0
        return round(min(1.0, room_p * 0.7 + boss_p * 0.3), 2)
    def status(self) -> Dict[str, Any]:
        return {
            "rooms": self.rooms_cleared,
            "packs": self.packs_cleared,
            "boss_phase": self.boss_phase,
            "boss_defeated": self.boss_defeated,
            "percent": self.percent(),
        }
