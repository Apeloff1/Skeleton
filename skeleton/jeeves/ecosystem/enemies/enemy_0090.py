"""Enemy 0090.
"""
from __future__ import annotations

ENEMY = "enemy_0090"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 90, "atk": 5 + (90 % 12), "def": 2 + (90 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
