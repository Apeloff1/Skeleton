"""Enemy 0013.
"""
from __future__ import annotations

ENEMY = "enemy_0013"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 13, "atk": 5 + (13 % 12), "def": 2 + (13 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
