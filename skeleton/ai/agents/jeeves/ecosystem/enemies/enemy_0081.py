"""Enemy 0081.
"""
from __future__ import annotations

ENEMY = "enemy_0081"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 81, "atk": 5 + (81 % 12), "def": 2 + (81 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
