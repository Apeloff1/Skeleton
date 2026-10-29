"""Enemy 0094.
"""
from __future__ import annotations

ENEMY = "enemy_0094"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 94, "atk": 5 + (94 % 12), "def": 2 + (94 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
