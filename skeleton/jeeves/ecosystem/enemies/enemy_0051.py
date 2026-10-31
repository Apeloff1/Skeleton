"""Enemy 0051.
"""
from __future__ import annotations

ENEMY = "enemy_0051"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 51, "atk": 5 + (51 % 12), "def": 2 + (51 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
