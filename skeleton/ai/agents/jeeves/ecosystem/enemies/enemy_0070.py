"""Enemy 0070.
"""
from __future__ import annotations

ENEMY = "enemy_0070"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 70, "atk": 5 + (70 % 12), "def": 2 + (70 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
