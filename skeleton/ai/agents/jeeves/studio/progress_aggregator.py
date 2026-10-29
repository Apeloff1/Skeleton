"""Progress aggregator.
Tracks rooms, packs, boss phase, defeat, and overall completion percentage.
"""
from typing import Any, Dict

class ProgressAggregator:
    def __init__(self):
        self.rooms = 0
        self.packs = 0
        self.boss_phase = 0
        self.boss_defeated = False

    def update(self, rooms: int = 0, packs: int = 0, boss_phase: int = 0, defeated: bool = False) -> None:
        self.rooms += rooms
        self.packs += packs
        self.boss_phase = max(self.boss_phase, boss_phase)
        if defeated:
            self.boss_defeated = True

    def percent(self) -> float:
        room_score = min(1.0, self.rooms / 10)
        pack_score = min(1.0, self.packs / 20)
        boss_score = 1.0 if self.boss_defeated else self.boss_phase / 5
        return round((room_score + pack_score + boss_score) / 3, 2)

    def status(self) -> Dict[str, Any]:
        return {
            "rooms": self.rooms,
            "packs": self.packs,
            "boss_phase": self.boss_phase,
            "boss_defeated": self.boss_defeated,
            "percent": self.percent(),
            "schema": "skeleton.progress.agg.v1",
        }
