"""Quest tracker.
Objectives, progress, optical/economy conditions, completion rewards.
"""
from __future__ import annotations
from typing import Any, Dict, List

QUESTS = [
    {"id": "clear_3", "desc": "Clear 3 packs", "target": 3, "type": "packs", "reward": 10},
    {"id": "salvage_20", "desc": "Collect 20 salvage", "target": 20, "type": "salvage", "reward": 15},
    {"id": "boss_phase_2", "desc": "Reach boss phase 2", "target": 2, "type": "boss", "reward": 25},
    {"id": "optical_high", "desc": "Maintain optical > 0.9", "target": 0.9, "type": "optical", "reward": 12},
]

class QuestTracker:
    def __init__(self):
        self.progress: Dict[str, float] = {q["id"]: 0.0 for q in QUESTS}
        self.completed: List[str] = []
    def update(self, packs: int = 0, salvage: int = 0, boss_phase: int = 0, optical: float = 0.0) -> List[str]:
        newly = []
        for q in QUESTS:
            if q["id"] in self.completed:
                continue
            if q["type"] == "packs":
                self.progress[q["id"]] = packs
            elif q["type"] == "salvage":
                self.progress[q["id"]] = salvage
            elif q["type"] == "boss":
                self.progress[q["id"]] = boss_phase
            elif q["type"] == "optical":
                self.progress[q["id"]] = optical
            if self.progress[q["id"]] >= q["target"]:
                self.completed.append(q["id"])
                newly.append(q["id"])
        return newly
    def status(self) -> Dict[str, Any]:
        return {"progress": self.progress, "completed": self.completed}
