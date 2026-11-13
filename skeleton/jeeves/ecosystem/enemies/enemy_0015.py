"""Enemy 0015.
"""
from __future__ import annotations

ENEMY = "enemy_0015"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 15, "atk": 5 + (15 % 12), "def": 2 + (15 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
