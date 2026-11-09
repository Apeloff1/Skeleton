"""Enemy 0011.
"""
from __future__ import annotations

ENEMY = "enemy_0011"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 11, "atk": 5 + (11 % 12), "def": 2 + (11 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
