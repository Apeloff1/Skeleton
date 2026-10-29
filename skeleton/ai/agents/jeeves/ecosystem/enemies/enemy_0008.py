"""Enemy 0008.
"""
from __future__ import annotations

ENEMY = "enemy_0008"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 8, "atk": 5 + (8 % 12), "def": 2 + (8 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
