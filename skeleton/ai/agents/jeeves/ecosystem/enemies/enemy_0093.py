"""Enemy 0093.
"""
from __future__ import annotations

ENEMY = "enemy_0093"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 93, "atk": 5 + (93 % 12), "def": 2 + (93 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
