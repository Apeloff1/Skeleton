"""Enemy 0005.
"""
from __future__ import annotations

ENEMY = "enemy_0005"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 5, "atk": 5 + (5 % 12), "def": 2 + (5 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
