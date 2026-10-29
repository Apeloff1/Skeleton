"""Enemy 0099.
"""
from __future__ import annotations

ENEMY = "enemy_0099"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 99, "atk": 5 + (99 % 12), "def": 2 + (99 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
