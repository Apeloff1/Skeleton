"""Enemy 0021.
"""
from __future__ import annotations

ENEMY = "enemy_0021"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 21, "atk": 5 + (21 % 12), "def": 2 + (21 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
