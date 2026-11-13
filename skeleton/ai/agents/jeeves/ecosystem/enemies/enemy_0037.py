"""Enemy 0037.
"""
from __future__ import annotations

ENEMY = "enemy_0037"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 37, "atk": 5 + (37 % 12), "def": 2 + (37 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
