"""Enemy 0025.
"""
from __future__ import annotations

ENEMY = "enemy_0025"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 25, "atk": 5 + (25 % 12), "def": 2 + (25 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
