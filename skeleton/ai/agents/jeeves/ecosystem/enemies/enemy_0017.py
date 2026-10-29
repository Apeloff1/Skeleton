"""Enemy 0017.
"""
from __future__ import annotations

ENEMY = "enemy_0017"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 17, "atk": 5 + (17 % 12), "def": 2 + (17 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
