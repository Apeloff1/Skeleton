"""Enemy 0075.
"""
from __future__ import annotations

ENEMY = "enemy_0075"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 75, "atk": 5 + (75 % 12), "def": 2 + (75 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
