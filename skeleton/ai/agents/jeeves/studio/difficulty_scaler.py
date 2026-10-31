"""Difficulty scaler.
Adjusts enemy health, pack value, boss aggression from optical feedback and player progress.
"""
from __future__ import annotations
from typing import Any, Dict

class DifficultyScaler:
    def scale(self, optical: float, rooms_cleared: int, base: float = 1.0) -> Dict[str, float]:
        ease = max(0.0, optical - 0.8) * 0.4
        pressure = rooms_cleared * 0.05
        mult = base + pressure - ease
        mult = max(0.6, min(1.8, mult))
        return {
            "enemy_health": round(1.0 * mult, 2),
            "pack_value": round(1.0 / mult, 2),
            "boss_aggression": round(0.7 + pressure * 0.5, 2),
            "overall": round(mult, 2),
        }
