"""Daily challenge.
Generates a constrained run goal from seed and optical target.
"""
from __future__ import annotations
from typing import Any, Dict
import random

class DailyChallenge:
    def __init__(self, seed: int = 8847291):
        self.rng = random.Random(seed)
    def generate(self) -> Dict[str, Any]:
        kinds = ["speedrun", "no_damage", "high_optical", "salvage_rush", "boss_only"]
        kind = self.rng.choice(kinds)
        target = {"speedrun": 120, "no_damage": 0, "high_optical": 0.96, "salvage_rush": 60, "boss_only": 1}[kind]
        return {
            "kind": kind,
            "target": target,
            "reward_mult": 1.5 if kind == "high_optical" else 1.2,
            "seed": self.rng.randint(1000, 9999),
        }
