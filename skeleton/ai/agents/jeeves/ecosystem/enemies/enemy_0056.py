"""Enemy 0056.
"""
from __future__ import annotations

ENEMY = "enemy_0056"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 56, "atk": 5 + (56 % 12), "def": 2 + (56 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
