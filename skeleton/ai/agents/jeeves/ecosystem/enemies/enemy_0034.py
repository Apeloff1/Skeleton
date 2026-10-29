"""Enemy 0034.
"""
from __future__ import annotations

ENEMY = "enemy_0034"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 34, "atk": 5 + (34 % 12), "def": 2 + (34 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
