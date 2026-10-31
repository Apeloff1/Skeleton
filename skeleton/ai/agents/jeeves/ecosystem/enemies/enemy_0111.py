"""Enemy 0111.
"""
from __future__ import annotations

ENEMY = "enemy_0111"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 111, "atk": 5 + (111 % 12), "def": 2 + (111 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
