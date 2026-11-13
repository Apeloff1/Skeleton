"""Enemy 0044.
"""
from __future__ import annotations

ENEMY = "enemy_0044"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 44, "atk": 5 + (44 % 12), "def": 2 + (44 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
