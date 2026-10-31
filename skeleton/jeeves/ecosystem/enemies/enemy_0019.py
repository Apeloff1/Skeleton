"""Enemy 0019.
"""
from __future__ import annotations

ENEMY = "enemy_0019"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 19, "atk": 5 + (19 % 12), "def": 2 + (19 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
