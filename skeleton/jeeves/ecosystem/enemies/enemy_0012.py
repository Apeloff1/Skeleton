"""Enemy 0012.
"""
from __future__ import annotations

ENEMY = "enemy_0012"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 12, "atk": 5 + (12 % 12), "def": 2 + (12 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
