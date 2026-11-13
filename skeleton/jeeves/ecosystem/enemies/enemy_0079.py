"""Enemy 0079.
"""
from __future__ import annotations

ENEMY = "enemy_0079"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 79, "atk": 5 + (79 % 12), "def": 2 + (79 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
