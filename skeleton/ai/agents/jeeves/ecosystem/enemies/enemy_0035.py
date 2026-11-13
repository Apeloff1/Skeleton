"""Enemy 0035.
"""
from __future__ import annotations

ENEMY = "enemy_0035"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 35, "atk": 5 + (35 % 12), "def": 2 + (35 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
