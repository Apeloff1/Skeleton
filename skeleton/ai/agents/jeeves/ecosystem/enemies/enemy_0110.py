"""Enemy 0110.
"""
from __future__ import annotations

ENEMY = "enemy_0110"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 110, "atk": 5 + (110 % 12), "def": 2 + (110 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
