"""Enemy 0084.
"""
from __future__ import annotations

ENEMY = "enemy_0084"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 84, "atk": 5 + (84 % 12), "def": 2 + (84 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
