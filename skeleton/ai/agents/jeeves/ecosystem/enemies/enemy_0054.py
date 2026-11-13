"""Enemy 0054.
"""
from __future__ import annotations

ENEMY = "enemy_0054"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 54, "atk": 5 + (54 % 12), "def": 2 + (54 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
