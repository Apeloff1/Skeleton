"""Enemy 0112.
"""
from __future__ import annotations

ENEMY = "enemy_0112"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 112, "atk": 5 + (112 % 12), "def": 2 + (112 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
