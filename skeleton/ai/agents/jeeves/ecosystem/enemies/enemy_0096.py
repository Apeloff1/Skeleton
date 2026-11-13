"""Enemy 0096.
"""
from __future__ import annotations

ENEMY = "enemy_0096"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 96, "atk": 5 + (96 % 12), "def": 2 + (96 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
