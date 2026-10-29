"""Enemy 0006.
"""
from __future__ import annotations

ENEMY = "enemy_0006"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 6, "atk": 5 + (6 % 12), "def": 2 + (6 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
