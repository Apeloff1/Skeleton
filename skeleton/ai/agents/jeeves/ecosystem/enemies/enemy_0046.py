"""Enemy 0046.
"""
from __future__ import annotations

ENEMY = "enemy_0046"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 46, "atk": 5 + (46 % 12), "def": 2 + (46 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
