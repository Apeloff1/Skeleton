"""Enemy 0028.
"""
from __future__ import annotations

ENEMY = "enemy_0028"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 28, "atk": 5 + (28 % 12), "def": 2 + (28 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
