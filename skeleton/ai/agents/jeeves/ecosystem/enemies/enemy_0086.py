"""Enemy 0086.
"""
from __future__ import annotations

ENEMY = "enemy_0086"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 86, "atk": 5 + (86 % 12), "def": 2 + (86 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
