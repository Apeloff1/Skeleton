"""Enemy 0049.
"""
from __future__ import annotations

ENEMY = "enemy_0049"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 49, "atk": 5 + (49 % 12), "def": 2 + (49 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
