"""Enemy 0074.
"""
from __future__ import annotations

ENEMY = "enemy_0074"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 74, "atk": 5 + (74 % 12), "def": 2 + (74 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
