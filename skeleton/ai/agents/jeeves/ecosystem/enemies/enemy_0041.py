"""Enemy 0041.
"""
from __future__ import annotations

ENEMY = "enemy_0041"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 41, "atk": 5 + (41 % 12), "def": 2 + (41 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
