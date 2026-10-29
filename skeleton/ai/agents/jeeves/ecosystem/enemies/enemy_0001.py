"""Enemy 0001.
"""
from __future__ import annotations

ENEMY = "enemy_0001"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 1, "atk": 5 + (1 % 12), "def": 2 + (1 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
