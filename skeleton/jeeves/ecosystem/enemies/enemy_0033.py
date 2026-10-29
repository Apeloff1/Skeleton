"""Enemy 0033.
"""
from __future__ import annotations

ENEMY = "enemy_0033"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 33, "atk": 5 + (33 % 12), "def": 2 + (33 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
