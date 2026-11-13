"""Enemy 0072.
"""
from __future__ import annotations

ENEMY = "enemy_0072"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 72, "atk": 5 + (72 % 12), "def": 2 + (72 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
