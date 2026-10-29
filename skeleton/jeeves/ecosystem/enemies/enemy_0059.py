"""Enemy 0059.
"""
from __future__ import annotations

ENEMY = "enemy_0059"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 59, "atk": 5 + (59 % 12), "def": 2 + (59 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
