"""Enemy 0009.
"""
from __future__ import annotations

ENEMY = "enemy_0009"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 9, "atk": 5 + (9 % 12), "def": 2 + (9 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
