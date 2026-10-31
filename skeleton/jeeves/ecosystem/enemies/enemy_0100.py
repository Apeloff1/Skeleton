"""Enemy 0100.
"""
from __future__ import annotations

ENEMY = "enemy_0100"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 100, "atk": 5 + (100 % 12), "def": 2 + (100 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
