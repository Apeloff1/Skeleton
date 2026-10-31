"""Enemy 0000.
"""
from __future__ import annotations

ENEMY = "enemy_0000"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 0, "atk": 5 + (0 % 12), "def": 2 + (0 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
