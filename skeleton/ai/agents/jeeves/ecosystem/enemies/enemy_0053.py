"""Enemy 0053.
"""
from __future__ import annotations

ENEMY = "enemy_0053"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 53, "atk": 5 + (53 % 12), "def": 2 + (53 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
