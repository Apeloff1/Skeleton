"""Enemy 0003.
"""
from __future__ import annotations

ENEMY = "enemy_0003"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 3, "atk": 5 + (3 % 12), "def": 2 + (3 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
