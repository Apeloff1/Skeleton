"""Enemy 0052.
"""
from __future__ import annotations

ENEMY = "enemy_0052"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 52, "atk": 5 + (52 % 12), "def": 2 + (52 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
