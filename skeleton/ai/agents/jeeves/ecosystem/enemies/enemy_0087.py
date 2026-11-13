"""Enemy 0087.
"""
from __future__ import annotations

ENEMY = "enemy_0087"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 87, "atk": 5 + (87 % 12), "def": 2 + (87 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
