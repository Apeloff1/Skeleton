"""Enemy 0004.
"""
from __future__ import annotations

ENEMY = "enemy_0004"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 4, "atk": 5 + (4 % 12), "def": 2 + (4 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
