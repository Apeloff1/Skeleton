"""Enemy 0069.
"""
from __future__ import annotations

ENEMY = "enemy_0069"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 69, "atk": 5 + (69 % 12), "def": 2 + (69 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
