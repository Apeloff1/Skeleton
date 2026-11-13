"""Enemy 0007.
"""
from __future__ import annotations

ENEMY = "enemy_0007"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 7, "atk": 5 + (7 % 12), "def": 2 + (7 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
