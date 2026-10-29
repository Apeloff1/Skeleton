"""Enemy 0068.
"""
from __future__ import annotations

ENEMY = "enemy_0068"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 68, "atk": 5 + (68 % 12), "def": 2 + (68 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
