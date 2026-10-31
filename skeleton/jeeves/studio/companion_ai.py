"""Companion AI.
Simple ally that follows, assists in combat, and reacts to optical state.
"""
from __future__ import annotations
from typing import Any, Dict, Tuple

class CompanionAI:
    def __init__(self):
        self.pos = (0.0, 0.0)
        self.health = 40.0
        self.mode = "follow"
    def update(self, player_pos: Tuple[float, float], optical: float, combat: bool = False) -> Dict[str, Any]:
        dx = player_pos[0] - self.pos[0]
        dy = player_pos[1] - self.pos[1]
        dist = (dx**2 + dy**2) ** 0.5 or 1.0
        if dist > 2.0:
            self.pos = (self.pos[0] + dx / dist * 0.8, self.pos[1] + dy / dist * 0.8)
        self.mode = "assist" if combat else "follow"
        if optical > 0.93:
            self.mode = "scout"
        return {"pos": self.pos, "mode": self.mode, "health": self.health}
    def assist_damage(self) -> float:
        return 6.0 if self.mode == "assist" else 0.0
