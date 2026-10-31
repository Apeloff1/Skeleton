"""Faction system.
Tracks standing with tunnel factions; affects loot, dialogue, and events.
"""
from __future__ import annotations
from typing import Any, Dict

class FactionSystem:
    def __init__(self):
        self.standing = {"ash_keepers": 0, "crystal_miners": 0, "void_watch": 0}
    def adjust(self, faction: str, delta: int) -> int:
        if faction in self.standing:
            self.standing[faction] = max(-100, min(100, self.standing[faction] + delta))
        return self.standing.get(faction, 0)
    def tier(self, faction: str) -> str:
        s = self.standing.get(faction, 0)
        if s >= 50:
            return "allied"
        if s >= 10:
            return "friendly"
        if s <= -50:
            return "hostile"
        if s <= -10:
            return "unfriendly"
        return "neutral"
    def status(self) -> Dict[str, Any]:
        return {f: {"standing": s, "tier": self.tier(f)} for f, s in self.standing.items()}
