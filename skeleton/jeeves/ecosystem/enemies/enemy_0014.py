"""Enemy 0014.
"""
from __future__ import annotations

ENEMY = "enemy_0014"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 14, "atk": 5 + (14 % 12), "def": 2 + (14 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
