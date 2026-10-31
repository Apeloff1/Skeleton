"""Enemy 0101.
"""
from __future__ import annotations

ENEMY = "enemy_0101"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 101, "atk": 5 + (101 % 12), "def": 2 + (101 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
