"""Enemy 0027.
"""
from __future__ import annotations

ENEMY = "enemy_0027"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 27, "atk": 5 + (27 % 12), "def": 2 + (27 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
