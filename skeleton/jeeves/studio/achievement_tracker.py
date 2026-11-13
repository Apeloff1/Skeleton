"""Achievement tracker.
Unlocks based on milestones across economy, combat, optical, and narrative.
"""
from __future__ import annotations
from typing import Any, Dict, List

ACHIEVEMENTS = [
    {"id": "first_pack", "desc": "Clear first pack", "check": "packs>=1"},
    {"id": "salvage_50", "desc": "Hold 50 salvage", "check": "salvage>=50"},
    {"id": "boss_down", "desc": "Defeat the boss", "check": "boss_defeated"},
    {"id": "optical_master", "desc": "Optical diversity > 0.95", "check": "optical>0.95"},
    {"id": "extract_rich", "desc": "Extract with high salvage", "check": "ending==extract_rich"},
    {"id": "full_quests", "desc": "Complete all quests", "check": "quests>=4"},
]

class AchievementTracker:
    def __init__(self):
        self.unlocked: List[str] = []
    def check(self, packs: int, salvage: int, boss_defeated: bool, optical: float, ending: str, quests: int) -> List[str]:
        newly = []
        for a in ACHIEVEMENTS:
            if a["id"] in self.unlocked:
                continue
            ok = False
            c = a["check"]
            if c == "packs>=1" and packs >= 1:
                ok = True
            elif c == "salvage>=50" and salvage >= 50:
                ok = True
            elif c == "boss_defeated" and boss_defeated:
                ok = True
            elif c == "optical>0.95" and optical > 0.95:
                ok = True
            elif c == "ending==extract_rich" and ending == "extract_rich":
                ok = True
            elif c == "quests>=4" and quests >= 4:
                ok = True
            if ok:
                self.unlocked.append(a["id"])
                newly.append(a["id"])
        return newly
    def status(self) -> Dict[str, Any]:
        return {"unlocked": self.unlocked, "total": len(ACHIEVEMENTS)}
