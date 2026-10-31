"""Boss phase sequencer (10x).
Multi-phase state machine, attack sequencing, weak points, optical tags, defeat conditions.
"""
from __future__ import annotations
from typing import Any, Dict, List

class BossSequencer:
    def __init__(self, phases: int = 5):
        self.phase = 0
        self.phases = phases
        self.health = phases * 40.0
        self.max = self.health
        self.weak_points = ["core", "arm", "core", "leg", "core"]
        self.sequence = ["dash", "spread", "denial", "summon", "beam"]

    def tick(self, dt: float, player_damage: float = 0.0) -> Dict[str, Any]:
        self.health = max(0.0, self.health - player_damage)
        thresh = 1.0 - (self.phase + 1) / self.phases
        if self.health < self.max * thresh and self.phase < self.phases - 1:
            self.phase += 1
        pattern = self.sequence[self.phase % len(self.sequence)]
        weak = self.weak_points[self.phase % len(self.weak_points)]
        defeated = self.health <= 0.0
        return {
            "phase": self.phase,
            "pattern": pattern,
            "weak_point": weak,
            "health": self.health,
            "defeated": defeated,
            "optical_tag": pattern,
        }
