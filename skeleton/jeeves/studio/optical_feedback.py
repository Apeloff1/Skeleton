"""Optical feedback loop (creative longform).
Modifies level difficulty, enemy density, salvage rates, and boss aggression from optical diversity and tile classes.
"""
from __future__ import annotations
from typing import Any, Dict

class OpticalFeedback:
    def apply(self, optical: float, classes: Dict[str, float], base_difficulty: float = 0.5) -> Dict[str, Any]:
        hazard = classes.get("tile_hazard", 0.1)
        pack = classes.get("entity_pack", 0.15)
        difficulty = base_difficulty + hazard * 0.4 - (optical - 0.8) * 0.3
        difficulty = max(0.2, min(0.95, difficulty))
        enemy_mult = 1.0 + hazard * 0.5
        salvage_mult = 1.0 + pack * 0.6 + (optical - 0.85) * 0.4
        boss_aggression = 0.6 + (1.0 - optical) * 0.3 + hazard * 0.2
        return {
            "difficulty": round(difficulty, 3),
            "enemy_mult": round(enemy_mult, 2),
            "salvage_mult": round(salvage_mult, 2),
            "boss_aggression": round(boss_aggression, 2),
            "optical": optical,
        }
