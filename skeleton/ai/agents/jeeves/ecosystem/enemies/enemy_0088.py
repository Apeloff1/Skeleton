"""Enemy 0088.
"""
from __future__ import annotations

ENEMY = "enemy_0088"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 88, "atk": 5 + (88 % 12), "def": 2 + (88 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
