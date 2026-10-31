"""Enemy 0030.
"""
from __future__ import annotations

ENEMY = "enemy_0030"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 30, "atk": 5 + (30 % 12), "def": 2 + (30 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
