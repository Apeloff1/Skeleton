"""Enemy 0023.
"""
from __future__ import annotations

ENEMY = "enemy_0023"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 23, "atk": 5 + (23 % 12), "def": 2 + (23 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
