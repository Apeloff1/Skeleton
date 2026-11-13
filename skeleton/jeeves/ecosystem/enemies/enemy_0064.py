"""Enemy 0064.
"""
from __future__ import annotations

ENEMY = "enemy_0064"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 64, "atk": 5 + (64 % 12), "def": 2 + (64 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
