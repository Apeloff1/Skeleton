"""Enemy 0010.
"""
from __future__ import annotations

ENEMY = "enemy_0010"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 10, "atk": 5 + (10 % 12), "def": 2 + (10 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
